"""chunks.json → embedding → HNSW indeksi

Kullanım:
    python rag/embed.py                 # .env › PROJECT
    python rag/embed.py --project <id>

Çıktılar (index/<proje-id>/):
  hnsw.bin     HNSW indeksi (hnswlib). Etiket i = index.json › chunks[i]
  index.json   chunk metinleri + metadata + embedding ve HNSW ayarları (vektörler hnsw.bin'de)

Ayarlar:
  project.json › embedding    model, passagePrefix, queryPrefix, batchSize (isteğe bağlı, varsayılan 32)
  project.json › vectorStore  space, M, efConstruction, efSearch
  project.json › retrieval    topK (recall kontrolünde kullanılır)

Kaydetmeden önce doğrular:
  - chunks.json güncel (chunking ayarları aynı, pages.json'dan eski değil, aynı tokenizer)
  - önek ve özel tokenlar dahil hiçbir chunk modelin token sınırını aşmıyor (aşan sessizce kesilirdi)
  - vektör sayısı = chunk sayısı, NaN yok, her vektörün normu 1
  - HNSW recall@topK = 1.0 (diskten okunan indeksin sonuçları kesin aramayla aynı)
Doğrulama başarısızsa hiçbir dosya yazılmaz ve hata koduyla çıkılır.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

import hnswlib
import numpy as np
from sentence_transformers import SentenceTransformer

from config import ROOT, ConfigError, cli_project

SCHEMA_VERSION = 2
NORM_TOLERANCE = 1e-3
HNSW_SEED = 100        # her çalıştırmada aynı graf oluşsun
HNSW_FILE = "hnsw.bin"


def stale_chunks_reason(project, chunk_data: dict, chunks_file, model: str) -> str | None:
    """chunks.json güncel değilse nedenini döndürür."""
    stored = chunk_data.get("chunking")
    if not isinstance(stored, dict):
        return "chunks.json chunking ayarlarını içermiyor."
    strip = lambda d: {k: v for k, v in d.items() if k != "tokenizer"}
    current = project.get("chunking")
    if strip(stored) != strip(current):
        changed = sorted(k for k in set(strip(stored)) | set(strip(current)) if stored.get(k) != current.get(k))
        return f"chunking ayarları değişmiş (farklı alanlar: {', '.join(changed)})."
    pages_file = project.index_dir / "pages.json"
    if pages_file.exists() and pages_file.stat().st_mtime > chunks_file.stat().st_mtime:
        return "pages.json, chunks.json'dan daha yeni (extract yeniden çalışmış)."
    if stored.get("tokenizer") and stored["tokenizer"] != model:
        return f"chunks.json '{stored['tokenizer']}' tokenizer'ıyla üretilmiş, embedding modeli '{model}'."
    return None


def recall_at_k(index: hnswlib.Index, vectors: np.ndarray, k: int) -> float:
    """Her chunk vektörünü soru gibi kullanır; HNSW'nin ilk k sonucunu kesin aramayla karşılaştırır."""
    labels, _ = index.knn_query(vectors, k=k)
    exact = np.argsort(-(vectors @ vectors.T), axis=1)[:, :k]
    hits = sum(len(set(a) & set(b)) for a, b in zip(labels, exact))
    return hits / (len(vectors) * k)


def main() -> int:
    try:
        project = cli_project("Chunk'ları embed eder ve HNSW indeksini kaydeder.")
        model_name = project.get("embedding.model")
        passage_prefix = project.get("embedding.passagePrefix")
        batch_size = int(project.get("embedding.batchSize", 32))
        vs = project.get("vectorStore")
        space, m, ef_c, ef_s = vs["space"], vs["M"], vs["efConstruction"], vs["efSearch"]
        top_k = project.get("retrieval.topK")
    except (ConfigError, KeyError) as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1

    chunks_file = project.index_dir / "chunks.json"
    if not chunks_file.exists():
        print(f"Bulunamadı: {chunks_file.relative_to(ROOT)}. Önce: python rag/chunk.py", file=sys.stderr)
        return 1
    chunk_data = json.loads(chunks_file.read_text(encoding="utf-8"))
    chunks = chunk_data["chunks"]
    if not chunks:
        print("chunks.json boş.", file=sys.stderr)
        return 1
    if reason := stale_chunks_reason(project, chunk_data, chunks_file, model_name):
        print(f"{reason} Önce chunking'i yeniden çalıştır: python rag/chunk.py", file=sys.stderr)
        return 1
    if ef_s < top_k:
        print(f"vectorStore.efSearch ({ef_s}) retrieval.topK'dan ({top_k}) küçük olamaz.", file=sys.stderr)
        return 1

    print(f"Proje: {project.id} | model: {model_name}")
    model = SentenceTransformer(model_name)
    dim, token_limit = model.get_embedding_dimension(), model.max_seq_length
    print(f"Boyut: {dim} | token sınırı: {token_limit}")

    texts = [passage_prefix + c["text"] for c in chunks]
    token_counts = [len(model.tokenizer.encode(t, add_special_tokens=True)) for t in texts]

    t0 = time.perf_counter()
    vectors = model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=True).astype(np.float32)
    print(f"{len(vectors)} chunk embed edildi ({time.perf_counter() - t0:.1f} sn)")

    # ---- vektör doğrulama
    errors = []
    if vectors.shape != (len(chunks), dim):
        errors.append(f"Vektör matrisi {vectors.shape}, beklenen ({len(chunks)}, {dim}).")
    if not np.isfinite(vectors).all():
        errors.append("Vektörlerde NaN/sonsuz değer var.")
    norms = np.linalg.norm(vectors, axis=1)
    for c, n in zip(chunks, norms):
        if abs(n - 1.0) > NORM_TOLERANCE:
            errors.append(f"{c['id']}: norm {n:.4f}, beklenen 1.0.")
    for c, n in zip(chunks, token_counts):
        if n > token_limit:
            errors.append(f"{c['id']}: {n} token > model sınırı {token_limit} (metin kesilirdi).")

    # ---- HNSW indeksi: kur, geçici dosyaya kaydet, diskten geri okuyup recall ölç
    out_dir = project.index_dir
    tmp_file = out_dir / (HNSW_FILE + ".tmp")
    recall = None
    if not errors:
        t0 = time.perf_counter()
        index = hnswlib.Index(space=space, dim=dim)
        index.init_index(max_elements=len(vectors), M=m, ef_construction=ef_c, random_seed=HNSW_SEED)
        index.add_items(vectors, np.arange(len(vectors)))
        index.save_index(str(tmp_file))
        build_sec = time.perf_counter() - t0

        loaded = hnswlib.Index(space=space, dim=dim)
        loaded.load_index(str(tmp_file))
        loaded.set_ef(ef_s)
        if loaded.get_current_count() != len(chunks):
            errors.append(f"HNSW'de {loaded.get_current_count()} öğe var, beklenen {len(chunks)}.")
        recall = recall_at_k(loaded, vectors, top_k)
        if recall < 1.0:
            errors.append(f"HNSW recall@{top_k} = {recall:.3f} < 1.0 → vectorStore.efSearch'ü artır.")

    if errors:
        tmp_file.unlink(missing_ok=True)
        print(f"\nDoğrulama BAŞARISIZ ({len(errors)} hata), dosyalar yazılmadı:", file=sys.stderr)
        for err in errors[:20]:
            print(f"  - {err}", file=sys.stderr)
        return 2

    tmp_file.replace(out_dir / HNSW_FILE)
    output = {
        "schemaVersion": SCHEMA_VERSION,
        "project": project.id,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # yalnızca vektörü belirleyen alanlar; batchSize gibi çalışma ayarları yazılmaz
        "embedding": {
            "model": model_name,
            "dimensions": dim,
            "normalized": True,
            "passagePrefix": passage_prefix,
            "queryPrefix": project.get("embedding.queryPrefix"),
        },
        "vectorStore": {"type": "hnsw", "file": HNSW_FILE, "space": space, "M": m,
                        "efConstruction": ef_c, "efSearch": ef_s, "seed": HNSW_SEED, "count": len(chunks)},
        "chunking": chunk_data["chunking"],
        "chunks": chunks,  # sıra önemli: HNSW etiketi i → chunks[i]
    }
    (out_dir / "index.json").write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\nDoğrulama: tamam")
    print(f"  Vektör sayısı = chunk sayısı: {len(vectors)}, boyut {dim}, normalize")
    print(f"  Önekli token (özel tokenlar dahil): en fazla {max(token_counts)} / {token_limit}")
    print(f"  HNSW (M={m}, efConstruction={ef_c}, efSearch={ef_s}) kuruldu: {build_sec * 1000:.0f} ms")
    print(f"  HNSW recall@{top_k} (kesin aramaya göre, {len(chunks)} sorgu): {recall:.3f}")
    for name in (HNSW_FILE, "index.json"):
        f = out_dir / name
        print(f"→ {f.relative_to(ROOT)} ({f.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
