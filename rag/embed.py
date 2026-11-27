"""chunks.json → embedding → vektör deposu (FAISS dosyaları veya PostgreSQL + pgvector; ikisi de kesin arama)

Kullanım:
    python rag/embed.py                 # .env › PROJECT
    python rag/embed.py --project <id>

Çıktılar, project.json › vectorStore.type'a göre:
  "flat" (index/<proje-id>/):
    faiss.index  FAISS IndexFlatIP. Vektör i = index.json › chunks[i]
    index.json   chunk metinleri + metadata + embedding ve vectorStore ayarları (vektörler faiss.index'te)
  "pgvector" (rag/pgstore.py, tablolar rag/schema.sql):
    rag_indexes  proje satırı (model, boyut, ayarlar)
    rag_chunks   chunk metni + metadata + embedding + position; eski satırlar silinip tek transaction'da yazılır
    Veritabanı açık olmalı: docker compose up -d

Neden flat: IndexFlatIP soruyu bütün vektörlerle karşılaştırır (kesin arama, ayar gerektirmez).
Vektörler normalize olduğu için iç çarpım (IP) = cosine benzerliği. Birkaç bin chunk'a kadar
yaklaşık aramadan (HNSW) daha hızlıdır; çok büyürse faiss.IndexHNSWFlat'e geçilebilir.

Ayarlar:
  project.json › embedding    model, passagePrefix, queryPrefix, batchSize (isteğe bağlı, varsayılan 32)
  project.json › vectorStore  type: "flat"
  project.json › retrieval    topK (kontrol aramasında kullanılır)

Kaydetmeden önce doğrular:
  - chunks.json güncel (chunking ayarları aynı, pages.json'dan eski değil, aynı tokenizer)
  - önek ve özel tokenlar dahil hiçbir chunk modelin token sınırını aşmıyor (aşan sessizce kesilirdi)
  - vektör sayısı = chunk sayısı, NaN yok, her vektörün normu 1
  - kaydedilen indeksin (diskten okunan FAISS / DB'deki satırlar) ilk topK sonucu, bellekteki vektörlerle
    yapılan kesin aramayla aynı
Doğrulama başarısızsa hiçbir şey yazılmaz (DB'de transaction geri alınır) ve hata koduyla çıkılır.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from config import ROOT, ConfigError, cli_project

SCHEMA_VERSION = 2
NORM_TOLERANCE = 1e-3
INDEX_FILE = "faiss.index"
SUPPORTED_TYPES = ("flat", "pgvector")


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


def search_matches_exact(index: faiss.Index, vectors: np.ndarray, k: int) -> float:
    """Her chunk vektörünü soru gibi kullanır; FAISS'in ilk k sonucunu numpy ile kesin aramayla karşılaştırır."""
    _, labels = index.search(vectors, k)
    exact = np.argsort(-(vectors @ vectors.T), axis=1)[:, :k]
    hits = sum(len(set(a) & set(b)) for a, b in zip(labels, exact))
    return hits / (len(vectors) * k)


def main() -> int:
    try:
        project = cli_project("Chunk'ları embed eder ve FAISS indeksini kaydeder.")
        model_name = project.get("embedding.model")
        passage_prefix = project.get("embedding.passagePrefix")
        batch_size = int(project.get("embedding.batchSize", 32))
        vs_type = project.get("vectorStore.type")
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
    if vs_type not in SUPPORTED_TYPES:
        print(f"vectorStore.type {vs_type!r} desteklenmiyor. Desteklenenler: {SUPPORTED_TYPES}", file=sys.stderr)
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

    if errors:
        print(f"\nDoğrulama BAŞARISIZ ({len(errors)} hata), hiçbir şey yazılmadı:", file=sys.stderr)
        for err in errors[:20]:
            print(f"  - {err}", file=sys.stderr)
        return 2

    embedding_info = {
        "model": model_name,
        "dimensions": dim,
        "normalized": True,
        "passagePrefix": passage_prefix,
        "queryPrefix": project.get("embedding.queryPrefix"),
    }
    if vs_type == "pgvector":
        return save_pgvector(project, embedding_info, chunk_data, chunks, vectors, top_k, token_counts, token_limit)

    # ---- FAISS indeksi: kur, geçici dosyaya kaydet, diskten geri okuyup kontrol et
    out_dir = project.index_dir
    tmp_file = out_dir / (INDEX_FILE + ".tmp")
    match = None
    if not errors:
        t0 = time.perf_counter()
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)
        faiss.write_index(index, str(tmp_file))
        build_sec = time.perf_counter() - t0

        loaded = faiss.read_index(str(tmp_file))
        if loaded.ntotal != len(chunks):
            errors.append(f"FAISS'te {loaded.ntotal} vektör var, beklenen {len(chunks)}.")
        match = search_matches_exact(loaded, vectors, top_k)
        if match < 1.0:
            errors.append(f"FAISS ilk {top_k} sonucu kesin aramayla uyuşmuyor ({match:.3f}).")

    if errors:
        tmp_file.unlink(missing_ok=True)
        print(f"\nDoğrulama BAŞARISIZ ({len(errors)} hata), dosyalar yazılmadı:", file=sys.stderr)
        for err in errors[:20]:
            print(f"  - {err}", file=sys.stderr)
        return 2

    tmp_file.replace(out_dir / INDEX_FILE)
    output = {
        "schemaVersion": SCHEMA_VERSION,
        "project": project.id,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # yalnızca vektörü belirleyen alanlar; batchSize gibi çalışma ayarları yazılmaz
        "embedding": embedding_info,
        "vectorStore": {"type": vs_type, "library": "faiss", "index": "IndexFlatIP", "metric": "inner_product",
                        "file": INDEX_FILE, "count": len(chunks)},
        "chunking": chunk_data["chunking"],
        "chunks": chunks,  # sıra önemli: FAISS vektörü i → chunks[i]
    }
    (out_dir / "index.json").write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\nDoğrulama: tamam")
    print(f"  Vektör sayısı = chunk sayısı: {len(vectors)}, boyut {dim}, normalize")
    print(f"  Önekli token (özel tokenlar dahil): en fazla {max(token_counts)} / {token_limit}")
    print(f"  FAISS IndexFlatIP kuruldu: {build_sec * 1000:.1f} ms")
    print(f"  Diskten okunan indeks, ilk {top_k} sonuçta kesin aramayla uyumlu ({len(chunks)} sorgu): {match:.3f}")
    for name in (INDEX_FILE, "index.json"):
        f = out_dir / name
        print(f"→ {f.relative_to(ROOT)} ({f.stat().st_size / 1e6:.2f} MB)")
    return 0


def save_pgvector(project, embedding_info, chunk_data, chunks, vectors, top_k, token_counts, token_limit) -> int:
    """Vektörleri PostgreSQL + pgvector'e yazar (rag/pgstore.py). Tek transaction: hata olursa eski indeks kalır."""
    import pgstore  # psycopg yalnızca bu yolda gerekir

    settings = {"schemaVersion": SCHEMA_VERSION, "embedding": embedding_info, "chunking": chunk_data["chunking"]}
    try:
        t0 = time.perf_counter()
        with pgstore.connect(apply_schema=True) as conn:
            result = pgstore.write_index(conn, project.id, embedding_info["model"], embedding_info["dimensions"],
                                         settings, chunks, vectors, top_k)
        write_sec = time.perf_counter() - t0
    except ConfigError as e:
        print(f"\nVeritabanına yazılamadı, eski indeks değişmedi: {e}", file=sys.stderr)
        return 2

    print("\nDoğrulama: tamam")
    print(f"  Vektör sayısı = chunk sayısı: {len(vectors)}, boyut {embedding_info['dimensions']}, normalize")
    print(f"  Önekli token (özel tokenlar dahil): en fazla {max(token_counts)} / {token_limit}")
    print(f"  PostgreSQL'e yazıldı ve doğrulandı: {write_sec:.1f} sn (tek transaction)")
    print(f"  DB araması, ilk {top_k} sonuçta kesin aramayla uyumlu ({len(chunks)} sorgu): {result['match']:.3f}"
          f", en büyük puan farkı {result['max_diff']:.1e}")
    print(f"→ rag_indexes / rag_chunks (project = '{project.id}', {result['count']} satır)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
