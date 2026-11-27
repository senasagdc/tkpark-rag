"""Retrieval (adım 7, LLM yok): soru → embedding → vektör deposu → en yakın K chunk.

Chatbot bu dosyadaki Retriever'ı kullanır (rag/answer.py). Ölçüm (Hit@K, MRR) burada değil:
python tests/retrieval_test.py

Kullanım:
    python rag/search.py "Ortak alanlar nasıl kullanılır?"
    python rag/search.py "soru" --top 10 --project <id>

Vektör deposu project.json › vectorStore.type ile seçilir (ikisini de embed.py üretir):
    "flat"      index/<proje-id>/index.json (chunk'lar) + faiss.index (vektörler; vektör i = chunks[i])
    "pgvector"  PostgreSQL tabloları rag_indexes + rag_chunks (rag/pgstore.py); docker compose up -d gerekir
Retriever'ın dışarıya verdikleri (search, chunks, section, title) depodan bağımsızdır;
answer.py ve tests/ hangi deponun kullanıldığını bilmez.

Ayarlar project.json'dan:
    embedding.model, embedding.queryPrefix
    retrieval.topK      gösterilecek sonuç sayısı (--top ile değiştirilebilir)
    retrieval.minScore  bu puanın altındaki sonuçlar "eşik altı" diye işaretlenir

    queryRewrite.*      adım 5, kural listesiyle soruyu belgenin diline yaklaştırma (rag/rewrite.py; --no-rewrite)

Puan = cosine benzerliği (vektörler normalize; FAISS'te iç çarpım, pgvector'de 1 - (embedding <=> soru)).
Soru yeniden yazıldıysa orijinal ve yeni soruyla ayrı ayrı aranır, sıralamalar RRF ile birleştirilir
(her chunk iki listedeki sırasına göre 1 / (60 + sıra) toplar); gösterilen puan chunk'ın iki aramadaki
en yüksek cosine puanıdır.
"""

from __future__ import annotations

import argparse
import json
import sys

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from config import ROOT, ConfigError, load_project

class FaissStore:
    """vectorStore.type = "flat": index.json + faiss.index dosyaları."""

    def __init__(self, project):
        index_file = project.index_dir / "index.json"
        if not index_file.exists():
            raise ConfigError(f"Bulunamadı: {index_file.relative_to(ROOT)}. Önce: python rag/embed.py")
        data = json.loads(index_file.read_text(encoding="utf-8"))
        self.where = "index.json"
        self.model = data["embedding"]["model"]
        self.chunks = data["chunks"]
        self.index = faiss.read_index(str(project.index_dir / data["vectorStore"]["file"]))
        self.dimensions = self.index.d
        if self.index.ntotal != len(self.chunks):
            raise ConfigError(
                f"faiss.index'te {self.index.ntotal} vektör, index.json'da {len(self.chunks)} chunk var. "
                "İndeksi yeniden oluştur: python rag/embed.py"
            )

    def search(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return self.index.search(q, self.index.ntotal)


class PgStore:
    """vectorStore.type = "pgvector": PostgreSQL tabloları (rag/pgstore.py). Chunk'lar açılışta bir kez okunur."""

    def __init__(self, project):
        import pgstore  # psycopg yalnızca bu yolda gerekir
        self._pg = pgstore
        self.project_id = project.id
        self.conn = pgstore.connect()
        info, self.chunks = pgstore.load_index(self.conn, project.id)
        self.where = "veritabanı (rag_indexes)"
        self.model, self.dimensions = info["model"], info["dimensions"]

    def search(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return self._pg.search(self.conn, self.project_id, q)


STORES = {"flat": FaissStore, "pgvector": PgStore}


RRF_K = 60  # Reciprocal Rank Fusion sabiti (literatürdeki yaygın değer)


def rrf_merge(lists: list[tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    """Birden çok (puanlar, id'ler) sıralamasını RRF ile birleştirir → (en yüksek cosine, id'ler), RRF'e göre sıralı."""
    rrf, best = {}, {}
    for scores, ids in lists:
        for rank, (s, i) in enumerate(zip(scores, ids), 1):
            i = int(i)
            rrf[i] = rrf.get(i, 0.0) + 1.0 / (RRF_K + rank)
            best[i] = max(best.get(i, -1.0), float(s))
    order = sorted(rrf, key=lambda i: (-rrf[i], -best[i]))
    return (np.asarray([best[i] for i in order], dtype=np.float32), np.asarray(order, dtype=np.int64))


class Retriever:
    def __init__(self, project, rewrite: bool | None = None):
        """rewrite: None → project.json › queryRewrite.enabled; True/False ayarı ezer (önce/sonra ölçümü için)."""
        store_type = project.get("vectorStore.type")
        if store_type not in STORES:
            raise ConfigError(f"vectorStore.type {store_type!r} desteklenmiyor. Desteklenenler: {tuple(STORES)}")
        self.store = STORES[store_type](project)

        # Soru ve chunk'lar aynı modelle embed edilmeli, yoksa puanlar anlamsız olur.
        model = project.get("embedding.model")
        if self.store.model != model:
            raise ConfigError(
                f"{self.store.where} modeli ({self.store.model}) project.json ile uyuşmuyor ({model}). "
                "İndeksi yeniden oluştur: python rag/embed.py"
            )
        self.chunks = self.store.chunks
        self.query_prefix = project.get("embedding.queryPrefix")
        self.model = SentenceTransformer(model)
        if self.model.get_embedding_dimension() != self.store.dimensions:
            raise ConfigError(
                f"Model {self.model.get_embedding_dimension()} boyutlu vektör üretiyor, {self.store.where} "
                f"{self.store.dimensions} boyutlu. İndeksi yeniden oluştur: python rag/embed.py"
            )

        if rewrite is None:
            rewrite = bool(project.get("queryRewrite.enabled", False))
        self.rewriter = None
        if rewrite:
            from rewrite import QueryRewriter
            self.rewriter = QueryRewriter(project)
        self.last_rewrites = []  # son aramada her soru için yeniden yazılmış hali (yoksa None)

    def search_dense(self, questions: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """Yalnızca embedding araması: her soru için TÜM chunk'lar cosine puanına göre sıralı."""
        q = self.model.encode([self.query_prefix + s for s in questions],
                              normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)
        return self.store.search(q)

    def search(self, questions: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """Her soru için TÜM chunk'ları puana göre sıralar → (puanlar, chunk sıra no'ları).

        Hepsini istiyoruz çünkü doğru bölüm ilk K'nın dışında kalsa bile kaçıncı sırada olduğunu görmek istiyoruz.
        Query rewriting açıksa ve soru yeniden yazıldıysa iki arama RRF ile birleştirilir (modül açıklaması).
        """
        rewrites = [self.rewriter.rewrite(q) if self.rewriter else None for q in questions]
        self.last_rewrites = rewrites
        extra = [rw for rw in rewrites if rw]
        scores, ids = self.search_dense(list(questions) + extra)
        n = len(questions)
        out_scores, out_ids = scores[:n].copy(), ids[:n].copy()
        j = n
        for qi, rw in enumerate(rewrites):
            if rw:
                out_scores[qi], out_ids[qi] = rrf_merge([(scores[qi], ids[qi]), (scores[j], ids[j])])
                j += 1
        return out_scores, out_ids

    def settings(self) -> dict:
        return {"queryRewrite": self.rewriter.settings() if self.rewriter else None}

    def section(self, i: int) -> str:
        return self.chunks[i]["metadata"].get("section") or "?"

    def title(self, i: int, width: int = 64) -> str:
        t = self.chunks[i]["metadata"].get("title", "")
        return t if len(t) <= width else t[: width - 1] + "…"


def print_results(r: Retriever, scores, ids, k: int, min_score: float, expected=()) -> None:
    for rank, (s, i) in enumerate(zip(scores[:k], ids[:k]), 1):
        mark = "✓" if r.section(i) in expected else " "
        below = "  (eşik altı)" if s < min_score else ""
        print(f"  {mark} {rank:>2}. {s:.4f}  {r.section(i):<9} {r.title(i)}{below}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Belgede arama (LLM yok).")
    parser.add_argument("question", help="aranacak soru")
    parser.add_argument("--top", type=int, help="gösterilecek sonuç sayısı (varsayılan: retrieval.topK)")
    parser.add_argument("--no-rewrite", action="store_true", help="query rewriting'i kapat")
    parser.add_argument("--project", help="projects/ altındaki proje klasörü (varsayılan: .env PROJECT)")
    args = parser.parse_args()

    try:
        project = load_project(args.project)
        k = args.top or int(project.get("retrieval.topK"))
        min_score = float(project.get("retrieval.minScore", 0.0))
        r = Retriever(project, rewrite=False if args.no_rewrite else None)
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1

    scores, ids = r.search([args.question])
    print(f"\n{args.question}")
    if r.last_rewrites[0]:
        print(f"  (yeniden yazıldı: {r.last_rewrites[0]})")
    print_results(r, scores[0], ids[0], k, min_score)
    return 0


if __name__ == "__main__":
    sys.exit(main())
