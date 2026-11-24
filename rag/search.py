"""Retrieval testi (LLM yok): soru → embedding → FAISS → en yakın K chunk.

Kullanım:
    python rag/search.py "Ortak alanlar nasıl kullanılır?"     # tek soru
    python rag/search.py --eval                                  # soru setiyle deney
    python rag/search.py --eval --top 10 --project <id>

Okunan dosyalar (index/<proje-id>/):
    index.json   chunk metinleri + metadata + embedding ayarları (embed.py üretir)
    faiss.index  vektörler; vektör i = index.json › chunks[i]

Ayarlar project.json'dan:
    embedding.model, embedding.queryPrefix
    retrieval.topK      gösterilecek sonuç sayısı (--top ile değiştirilebilir)
    retrieval.minScore  bu puanın altındaki sonuçlar "eşik altı" diye işaretlenir
    eval.retrieval      soru seti yolu (varsayılan: eval/retrieval.jsonl, proje klasörüne göre)

Soru seti JSONL, her satır:
    {"id": "q01", "question": "...", "expected": ["10.1"], "difficulty": "zor"}
    expected = doğru sayılan metadata.section değerleri. Boş liste = belgede cevabı olmayan soru;
    bunlar difficulty etiketine göre ("konu dışı", "cevapsız") ayrı gruplarda raporlanır.

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

DEFAULT_EVAL_FILE = "eval/retrieval.jsonl"
HIT_AT = (1, 3, 5)


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


def load_eval(project) -> list[dict]:
    path = project.path(project.get("eval.retrieval", DEFAULT_EVAL_FILE))
    if not path.exists():
        raise ConfigError(f"Soru seti bulunamadı: {path.relative_to(ROOT)}")
    items = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as e:
            raise ConfigError(f"{path.name}:{line_no}: geçersiz JSON ({e})") from e
        if not item.get("question") or not isinstance(item.get("expected"), list):
            raise ConfigError(f"{path.name}:{line_no}: 'question' ve 'expected' (liste) zorunlu.")
        items.append(item)
    return items


def run_eval(r: Retriever, items: list[dict], k: int, min_score: float) -> int:
    known = {c["metadata"].get("section") for c in r.chunks}
    unknown = [(it["id"], s) for it in items for s in it["expected"] if s not in known]
    if unknown:
        print(f"Uyarı: indekste olmayan beklenen bölümler: {unknown}", file=sys.stderr)

    all_scores, all_ids = r.search([it["question"] for it in items])
    answerable, unanswerable = [], []

    for it, scores, ids in zip(items, all_scores, all_ids):
        print(f"\n[{it['id']}] {it['question']}  ({it.get('difficulty', '')})")
        top = float(scores[0])
        if it["expected"]:
            # beklenen bölümden gelen ilk chunk'ın sırası ve puanı
            hit = next(((rank, float(s)) for rank, (s, i) in enumerate(zip(scores, ids), 1)
                        if r.section(i) in it["expected"]), (None, None))
            rank, correct = hit
            status = f"doğru bölüm {rank}. sırada" if rank else "doğru bölüm yok"
            print(f"  beklenen: {', '.join(it['expected'])} → {status}")
            answerable.append({"id": it["id"], "rank": rank, "top": top, "correct": correct})
        else:
            unanswerable.append({"id": it["id"], "top": top, "group": it.get("difficulty") or "beklenen yok"})
        print_results(r, scores, ids, k, min_score, it["expected"])

    # ---- özet
    print("\n" + "=" * 72)
    n = len(answerable)
    if n:
        print(f"Cevabı belgede olan sorular: {n}")
        for h in HIT_AT:
            hits = sum(1 for a in answerable if a["rank"] and a["rank"] <= h)
            print(f"  Hit@{h}: {hits}/{n}  ({hits / n:.0%})")
        mrr = sum(1 / a["rank"] for a in answerable if a["rank"]) / n
        print(f"  MRR   : {mrr:.3f}   (1.0 = doğru bölüm hep 1. sırada)")
        missed = [f"{a['id']} ({a['rank']}.)" for a in answerable if not a["rank"] or a["rank"] > k]
        print(f"  İlk {k}'te olmayanlar: {', '.join(missed) if missed else 'yok'}")
        tops = [a["top"] for a in answerable]
        corrects = [a["correct"] for a in answerable if a["correct"] is not None]
        print(f"  1. sonucun puanı        : min {min(tops):.4f} / max {max(tops):.4f}")
        print(f"  Doğru bölümün puanı     : min {min(corrects):.4f} / max {max(corrects):.4f}")

    # Cevabı olmayan sorular: 1. sonuçlarının puanı, cevabı olan sorularınkinden düşük mü?
    # Düşükse minScore ile ayrılabilirler; değilse bunu LLM ("bilgim yok") yakalamalı.
    low = min(a["top"] for a in answerable) if n else None
    groups: dict[str, list[dict]] = {}
    for u in unanswerable:
        groups.setdefault(u["group"], []).append(u)
    for name, rows in groups.items():
        tops = [u["top"] for u in rows]
        print(f"Cevabı belgede olmayan ({name}): {len(rows)}")
        print(f"  1. sonucun puanı        : min {min(tops):.4f} / max {max(tops):.4f}")
        if low is None:
            continue
        leaked = [f"{u['id']} ({u['top']:.4f})" for u in rows if u["top"] >= low]
        if leaked:
            print(f"  Ayrım YOK: cevaplı sorulardan ayrılamayanlar: {', '.join(leaked)}"
                  " → bunları minScore değil LLM ('bilgim yok') yakalamalı.")
        else:
            print(f"  Ayrım VAR: cevaplı ≥ {low:.4f} > {name} ≤ {max(tops):.4f}"
                  f" (boşluk {low - max(tops):.4f}) → minScore bu aralıktan seçilebilir.")
    print(f"Ayarlar: topK={k}, minScore={min_score}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval testi (LLM yok).")
    parser.add_argument("question", nargs="?", help="aranacak soru")
    parser.add_argument("--eval", action="store_true", help="proje soru setiyle deneyi çalıştır")
    parser.add_argument("--top", type=int, help="gösterilecek sonuç sayısı (varsayılan: retrieval.topK)")
    parser.add_argument("--project", help="projects/ altındaki proje klasörü (varsayılan: .env PROJECT)")
    args = parser.parse_args()
    if not args.question and not args.eval:
        parser.error("bir soru ver ya da --eval kullan")

    try:
        project = load_project(args.project)
        k = args.top or int(project.get("retrieval.topK"))
        min_score = float(project.get("retrieval.minScore", 0.0))
        r = Retriever(project)
        if args.eval:
            return run_eval(r, load_eval(project), k, min_score)
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1

    scores, ids = r.search([args.question])
    print(f"\n{args.question}")
    print_results(r, scores[0], ids[0], k, min_score)
    return 0


if __name__ == "__main__":
    sys.exit(main())
