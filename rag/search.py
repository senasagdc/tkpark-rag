"""Retrieval (adım 7, LLM yok): soru → embedding → FAISS → en yakın K chunk.

Chatbot bu dosyadaki Retriever'ı kullanır (rag/answer.py). Ölçüm (Hit@K, MRR) burada değil:
python tests/retrieval_test.py

Kullanım:
    python rag/search.py "Ortak alanlar nasıl kullanılır?"
    python rag/search.py "soru" --top 10 --project <id>

Okunan dosyalar (index/<proje-id>/):
    index.json   chunk metinleri + metadata + embedding ayarları (embed.py üretir)
    faiss.index  vektörler; vektör i = index.json › chunks[i]

Ayarlar project.json'dan:
    embedding.model, embedding.queryPrefix
    retrieval.topK      gösterilecek sonuç sayısı (--top ile değiştirilebilir)
    retrieval.minScore  bu puanın altındaki sonuçlar "eşik altı" diye işaretlenir

Puan = cosine benzerliği (vektörler normalize, FAISS IndexFlatIP iç çarpımı).
"""

from __future__ import annotations

import argparse
import json
import sys

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from config import ROOT, ConfigError, load_project

class Retriever:
    def __init__(self, project):
        index_file = project.index_dir / "index.json"
        if not index_file.exists():
            raise ConfigError(f"Bulunamadı: {index_file.relative_to(ROOT)}. Önce: python rag/embed.py")
        data = json.loads(index_file.read_text(encoding="utf-8"))

        # Soru ve chunk'lar aynı modelle embed edilmeli, yoksa puanlar anlamsız olur.
        model = project.get("embedding.model")
        if data["embedding"]["model"] != model:
            raise ConfigError(
                f"index.json modeli ({data['embedding']['model']}) project.json ile uyuşmuyor ({model}). "
                "İndeksi yeniden oluştur: python rag/embed.py"
            )

        self.chunks = data["chunks"]
        self.index = faiss.read_index(str(project.index_dir / data["vectorStore"]["file"]))
        if self.index.ntotal != len(self.chunks):
            raise ConfigError(
                f"faiss.index'te {self.index.ntotal} vektör, index.json'da {len(self.chunks)} chunk var. "
                "İndeksi yeniden oluştur: python rag/embed.py"
            )
        self.query_prefix = project.get("embedding.queryPrefix")
        self.model = SentenceTransformer(model)

    def search(self, questions: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """Her soru için TÜM chunk'ları puana göre sıralar → (puanlar, chunk sıra no'ları).

        Hepsini istiyoruz çünkü doğru bölüm ilk K'nın dışında kalsa bile kaçıncı sırada olduğunu görmek istiyoruz.
        """
        q = self.model.encode([self.query_prefix + s for s in questions],
                              normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)
        return self.index.search(q, self.index.ntotal)

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
