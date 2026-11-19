"""chunks.json → embedding → index/<proje-id>/index.json

Kullanım:
    python rag/embed.py                 # .env › PROJECT
    python rag/embed.py --project <id>

Sağlayıcı ve model project.json › embedding'den okunur. Kaydetmeden önce doğrular:
  - vektör sayısı = chunk sayısı
  - tüm vektörler aynı boyutta (sağlayıcının bildirdiği boyut) ve sonlu sayılardan oluşuyor
  - sağlayıcı normalize diyorsa her vektörün normu 1
  - önek ve özel tokenlar dahil hiçbir chunk modelin token sınırını aşmıyor (aşan sessizce kesilirdi)
  - chunks.json, project.json'daki embedding modeliyle aynı tokenizer'la üretilmiş
  - chunks.json güncel: chunking ayarları project.json ile aynı, pages.json'dan eski değil
index.json › embedding'e yalnızca vektörü belirleyen alanlar yazılır (provider, model,
dimensions, normalized); batchSize gibi çalışma ayarları yazılmaz.
Doğrulama başarısızsa index.json yazılmaz ve hata koduyla çıkılır.
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone

from config import ROOT, ConfigError, cli_project
from providers import get_provider

SCHEMA_VERSION = 1
NORM_TOLERANCE = 1e-3
VECTOR_DECIMALS = 7  # float32 hassasiyeti; dosya boyutunu yarıya indirir


def validate(chunks: list[dict], vectors: list[list[float]], token_counts: list[int], provider) -> list[str]:
    errors: list[str] = []
    if len(vectors) != len(chunks):
        errors.append(f"Vektör sayısı ({len(vectors)}) chunk sayısından ({len(chunks)}) farklı.")

    for c, v in zip(chunks, vectors):
        if len(v) != provider.dimensions:
            errors.append(f"{c['id']}: boyut {len(v)}, beklenen {provider.dimensions}.")
            continue
        if not all(math.isfinite(x) for x in v):
            errors.append(f"{c['id']}: vektörde NaN/sonsuz değer var.")
            continue
        if provider.normalized:
            norm = math.sqrt(sum(x * x for x in v))
            if abs(norm - 1.0) > NORM_TOLERANCE:
                errors.append(f"{c['id']}: norm {norm:.4f}, beklenen 1.0.")

    if provider.token_limit:
        for c, n in zip(chunks, token_counts):
            if n > provider.token_limit:
                errors.append(f"{c['id']}: {n} token > model sınırı {provider.token_limit} (metin kesilirdi).")
    return errors


def main() -> int:
    # Çıktı dosyaya/pipe'a yönlendirilince Windows yerel kod sayfasını (cp1254) kullanır → UTF-8'e zorla.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        project = cli_project("Chunk'ları embed eder ve indeksi kaydeder.")
        emb_cfg = project.get("embedding")
    except ConfigError as e:
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

    # chunks.json eski mi? (project.json › chunking değişti ya da extract yeniden çalıştı ama chunk.py çalışmadı)
    rerun = "Önce chunking'i yeniden çalıştır: python rag/chunk.py"
    stored_chunking = chunk_data.get("chunking")
    if not isinstance(stored_chunking, dict):
        print(f"chunks.json chunking ayarlarını içermiyor. {rerun}", file=sys.stderr)
        return 1
    current_chunking = project.get("chunking")
    strip = lambda d: {k: v for k, v in d.items() if k != "tokenizer"}  # tokenizer aşağıda ayrıca kontrol edilir
    if strip(stored_chunking) != strip(current_chunking):
        changed = sorted(
            k for k in set(strip(stored_chunking)) | set(strip(current_chunking))
            if stored_chunking.get(k) != current_chunking.get(k)
        )
        print(
            f"chunks.json, project.json'daki güncel chunking ayarlarıyla üretilmemiş "
            f"(farklı alanlar: {', '.join(changed)}). {rerun}",
            file=sys.stderr,
        )
        return 1
    pages_file = project.index_dir / "pages.json"
    if pages_file.exists() and pages_file.stat().st_mtime > chunks_file.stat().st_mtime:
        print(f"pages.json, chunks.json'dan daha yeni (extract yeniden çalışmış). {rerun}", file=sys.stderr)
        return 1

    # chunking token sayımı farklı bir tokenizer'la yapıldıysa maxTokens garantisi geçersizdir
    chunk_tokenizer = stored_chunking.get("tokenizer")
    if chunk_tokenizer and chunk_tokenizer != emb_cfg.get("model"):
        print(
            f"chunks.json '{chunk_tokenizer}' tokenizer'ıyla üretilmiş, embedding modeli "
            f"'{emb_cfg.get('model')}'. Önce chunking'i yeniden çalıştır: python rag/chunk.py",
            file=sys.stderr,
        )
        return 1

    print(f"Proje: {project.id} | sağlayıcı: {emb_cfg.get('provider')} | model: {emb_cfg.get('model')}")
    try:
        provider = get_provider(emb_cfg)
    except (ValueError, OSError) as e:
        print(f"Sağlayıcı yüklenemedi: {e}", file=sys.stderr)
        return 1
    print(f"Boyut: {provider.dimensions} | normalize: {provider.normalized} | token sınırı: {provider.token_limit}")

    texts = [c["text"] for c in chunks]
    token_counts = provider.count_tokens(texts, "document")

    t0 = time.perf_counter()
    vectors = provider.embed(texts, "document")
    elapsed = time.perf_counter() - t0
    print(f"{len(vectors)} chunk embed edildi ({elapsed:.1f} sn)")

    errors = validate(chunks, vectors, token_counts, provider)
    if errors:
        print(f"\nDoğrulama BAŞARISIZ ({len(errors)} hata), index.json yazılmadı:", file=sys.stderr)
        for err in errors[:20]:
            print(f"  - {err}", file=sys.stderr)
        return 2

    output = {
        "schemaVersion": SCHEMA_VERSION,
        "project": project.id,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # yalnızca vektörü belirleyen alanlar; batchSize gibi çalışma ayarları yazılmaz
        "embedding": {
            "provider": emb_cfg.get("provider"),
            "model": emb_cfg.get("model"),
            "dimensions": provider.dimensions,
            "normalized": provider.normalized,
        },
        "chunking": chunk_data.get("chunking"),
        "chunks": [
            {
                "id": c["id"],
                "text": c["text"],
                "vector": [round(x, VECTOR_DECIMALS) for x in v],
                "metadata": c["metadata"],
            }
            for c, v in zip(chunks, vectors)
        ],
    }

    out_file = project.index_dir / "index.json"
    out_file.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")

    print("\nDoğrulama: tamam")
    print(f"  Vektör sayısı = chunk sayısı: {len(vectors)}")
    print(f"  Boyut: {provider.dimensions}, normalize: {provider.normalized}")
    print(f"  Önekli token (özel tokenlar dahil): en fazla {max(token_counts)} / {provider.token_limit}")
    size_mb = out_file.stat().st_size / 1e6
    print(f"\n→ {out_file.relative_to(ROOT)} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
