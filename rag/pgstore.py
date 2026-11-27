"""PostgreSQL + pgvector vektör deposu (project.json › vectorStore.type = "pgvector").

FAISS dosyalarının (index.json + faiss.index) veritabanındaki karşılığı. Tablolar rag/schema.sql'de:
    rag_indexes  proje başına 1 satır: model, boyut, ayarlar (index.json'ın üst kısmı)
    rag_chunks   chunk başına 1 satır: metin, metadata, embedding ve position (= index.json › chunks sırası)

Kullananlar:
    embed.py   write_index()  — eski satırları siler, yenilerini yazar, doğrular; hepsi tek transaction
    search.py  load_index() + search()  — Retriever'ın FAISS'le aynı sonucu döndürmesi için

Bağlantı bilgisi config.db_settings()'ten (docker/db.env veya DATABASE_URL).
Arama kesin (exact): rag_chunks'ta vektör indeksi (HNSW) yok, PostgreSQL bütün satırlara bakar;
yani sonuç FAISS IndexFlatIP ile aynıdır. Puan = 1 - cosine mesafesi (<=>).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from config import ConfigError, db_settings

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
CHECK_TOLERANCE = 1e-4  # DB puanı ile numpy iç çarpımı arasındaki izin verilen fark (float32)


def connect(apply_schema: bool = False):
    """Veritabanına bağlanır. apply_schema=True: schema.sql'i çalıştırır (IF NOT EXISTS, tekrar zararsız)."""
    import psycopg
    from pgvector.psycopg import register_vector

    try:
        conn = psycopg.connect(**db_settings(), connect_timeout=5, autocommit=True)
    except psycopg.OperationalError as e:
        first = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
        raise ConfigError(
            f"Veritabanına bağlanılamadı ({first}). Docker açık mı? Proje klasöründe: docker compose up -d"
        ) from e
    if apply_schema:
        conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
    try:
        register_vector(conn)  # numpy dizisi <-> vector tipi
    except psycopg.ProgrammingError as e:
        conn.close()
        raise ConfigError("Veritabanında pgvector eklentisi açık değil. Önce: python rag/embed.py") from e
    return conn


def write_index(conn, project_id: str, model: str, dimensions: int, settings: dict,
                chunks: list[dict], vectors: np.ndarray, top_k: int) -> dict:
    """Projenin indeksini baştan yazar ve doğrular. Doğrulama başarısızsa ConfigError; hiçbir şey değişmez.

    Hepsi tek transaction: önce eski satırlar silinir (ON DELETE CASCADE chunk'ları da siler), sonra
    yeniler yazılır ve okunarak kontrol edilir. Hata olursa ROLLBACK, eski indeks yerinde kalır.
    """
    if len(chunks) != len(vectors):
        raise ConfigError(f"{len(chunks)} chunk ama {len(vectors)} vektör.")
    with conn.transaction():
        conn.execute("DELETE FROM rag_indexes WHERE project = %s", (project_id,))
        conn.execute(
            "INSERT INTO rag_indexes (project, model, dimensions, settings, chunk_count) VALUES (%s, %s, %s, %s, %s)",
            (project_id, model, dimensions, json.dumps(settings, ensure_ascii=False), len(chunks)),
        )
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO rag_chunks (project, chunk_id, position, text, tokens, metadata, embedding)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                [(project_id, c["id"], i, c["text"], c["tokens"], json.dumps(c["metadata"], ensure_ascii=False), v)
                 for i, (c, v) in enumerate(zip(chunks, vectors))],
            )

        # ---- doğrulama (aynı transaction içinde; başarısızsa exception → ROLLBACK)
        count, dmin, dmax = conn.execute(
            "SELECT count(*), min(vector_dims(embedding)), max(vector_dims(embedding))"
            " FROM rag_chunks WHERE project = %s", (project_id,)).fetchone()
        if count != len(chunks) or dmin != dimensions or dmax != dimensions:
            raise ConfigError(f"Yazılan: {count} satır, boyut {dmin}–{dmax}; beklenen {len(chunks)} satır, boyut {dimensions}.")
        match, max_diff = _search_matches_exact(conn, project_id, vectors, top_k)
        if match < 1.0 or max_diff > CHECK_TOLERANCE:
            raise ConfigError(f"DB araması kesin aramayla uyuşmuyor (ilk {top_k} uyumu {match:.3f}, puan farkı {max_diff:.2e}).")
    return {"count": count, "match": match, "max_diff": max_diff}


def _search_matches_exact(conn, project_id: str, vectors: np.ndarray, k: int) -> tuple[float, float]:
    """Her chunk vektörünü soru gibi kullanır; DB'nin ilk k sonucunu numpy kesin aramasıyla karşılaştırır."""
    sims = vectors @ vectors.T
    exact = np.argsort(-sims, axis=1)[:, :k]
    hits, max_diff = 0, 0.0
    for i, v in enumerate(vectors):
        rows = conn.execute(
            "SELECT position, 1 - (embedding <=> %s) FROM rag_chunks WHERE project = %s"
            " ORDER BY embedding <=> %s LIMIT %s", (v, project_id, v, k)).fetchall()
        hits += len({r[0] for r in rows} & set(exact[i]))
        max_diff = max(max_diff, max(abs(score - sims[i, pos]) for pos, score in rows))
    return hits / (len(vectors) * k), float(max_diff)


def load_index(conn, project_id: str) -> tuple[dict, list[dict]]:
    """→ (rag_indexes satırı, chunk listesi). Chunk'lar position sırasında, index.json › chunks ile aynı biçimde."""
    info = conn.execute(
        "SELECT model, dimensions, settings, chunk_count, created_at FROM rag_indexes WHERE project = %s",
        (project_id,)).fetchone()
    if info is None:
        raise ConfigError(f"Veritabanında '{project_id}' indeksi yok. Önce: python rag/embed.py")
    model, dimensions, settings, chunk_count, created_at = info
    rows = conn.execute(
        "SELECT position, chunk_id, text, tokens, metadata FROM rag_chunks WHERE project = %s ORDER BY position",
        (project_id,)).fetchall()
    if [r[0] for r in rows] != list(range(chunk_count)):
        raise ConfigError(f"rag_chunks '{project_id}': position 0..{chunk_count - 1} değil "
                          f"({len(rows)} satır). İndeksi yeniden oluştur: python rag/embed.py")
    chunks = [{"id": cid, "text": text, "tokens": tokens, "metadata": meta} for _, cid, text, tokens, meta in rows]
    return ({"model": model, "dimensions": dimensions, "settings": settings,
             "count": chunk_count, "createdAt": created_at.isoformat()}, chunks)


def search(conn, project_id: str, queries: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Her soru için TÜM chunk'ları benzerliğe göre sıralar → (puanlar, position'lar); FAISS index.search ile aynı biçim."""
    all_scores, all_ids = [], []
    for q in queries:
        rows = conn.execute(
            "SELECT position, 1 - (embedding <=> %s) FROM rag_chunks WHERE project = %s ORDER BY embedding <=> %s",
            (q, project_id, q)).fetchall()
        all_ids.append([r[0] for r in rows])
        all_scores.append([r[1] for r in rows])
    return np.asarray(all_scores, dtype=np.float32), np.asarray(all_ids, dtype=np.int64)
