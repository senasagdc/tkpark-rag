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

Puan = cosine benzerliği (vektörler normalize; FAISS'te iç çarpım, pgvector'de 1 - (embedding <=> soru)).
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


class Retriever:
    def __init__(self, project):
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

    def search(self, questions: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """Her soru için TÜM chunk'ları puana göre sıralar → (puanlar, chunk sıra no'ları).

        Hepsini istiyoruz çünkü doğru bölüm ilk K'nın dışında kalsa bile kaçıncı sırada olduğunu görmek istiyoruz.
        """
        q = self.model.encode([self.query_prefix + s for s in questions],
                              normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)
        return self.store.search(q)

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
    parser.add_argument("--project", help="projects/ altındaki proje klasörü (varsayılan: .env PROJECT)")
    args = parser.parse_args()

    try:
        project = load_project(args.project)
        k = args.top or int(project.get("retrieval.topK"))
        min_score = float(project.get("retrieval.minScore", 0.0))
        r = Retriever(project)
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1

    scores, ids = r.search([args.question])
    print(f"\n{args.question}")
    print_results(r, scores[0], ids[0], k, min_score)
    return 0


if __name__ == "__main__":
    sys.exit(main())
