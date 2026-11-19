"""Retrieval testi (LLM yok): soru → embedding → cosine benzerliği → en iyi K chunk.

Kullanım:
    python rag/search.py "Ortak alanlar nasıl kullanılır?"     # tek soru
    python rag/search.py --eval                                  # soru setiyle deney
    python rag/search.py --eval --top 10 --project <id>

Ayarlar project.json'dan okunur:
    retrieval.topK      varsayılan K (--top ile ezilebilir)
    retrieval.minScore  bu puanın altındaki sonuçlar "eşik altı" olarak işaretlenir
    eval.retrieval      soru seti yolu (varsayılan: eval/retrieval.jsonl, proje klasörüne göre)

Soru seti JSONL, her satır:
    {"id": "q01", "question": "...", "expected": ["10.1"], "difficulty": "zor"}
    expected = doğru sayılan metadata.section değerleri; boş liste = konu dışı soru.

Vektörler normalize olduğu için cosine benzerliği = dot product. Tüm chunk'lar
tek tek karşılaştırılır (brute-force / exact kNN); birkaç bin chunk'a kadar yeterli.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from config import ROOT, ConfigError, load_project
from providers import get_provider

DEFAULT_EVAL_FILE = "eval/retrieval.jsonl"
HIT_AT = (1, 3, 5)


class Index:
    def __init__(self, project, provider):
        path = project.index_dir / "index.json"
        if not path.exists():
            raise ConfigError(f"Bulunamadı: {path.relative_to(ROOT)}. Önce: python rag/embed.py")
        data = json.loads(path.read_text(encoding="utf-8"))

        stored = data.get("embedding", {})
        for key in ("provider", "model"):
            if stored.get(key) != project.get(f"embedding.{key}"):
                raise ConfigError(
                    f"index.json embedding.{key} ({stored.get(key)!r}) project.json ile uyuşmuyor "
                    f"({project.get(f'embedding.{key}')!r}). İndeksi yeniden oluştur: python rag/embed.py"
                )

        self.chunks = data["chunks"]
        self.matrix = np.asarray([c["vector"] for c in self.chunks], dtype=np.float32)
        self.provider = provider
        if not provider.normalized:
            norms = np.linalg.norm(self.matrix, axis=1, keepdims=True)
            self.matrix = self.matrix / np.clip(norms, 1e-12, None)

    def search_many(self, questions: list[str]) -> np.ndarray:
        """Her soru için tüm chunk'lara puan döner: (soru sayısı × chunk sayısı)."""
        q = np.asarray(self.provider.embed(questions, kind="query"), dtype=np.float32)
        if not self.provider.normalized:
            q = q / np.clip(np.linalg.norm(q, axis=1, keepdims=True), 1e-12, None)
        return q @ self.matrix.T


def short(chunk: dict, width: int = 70) -> str:
    title = chunk["metadata"].get("title", "")
    return title if len(title) <= width else title[: width - 1] + "…"


def print_results(index: Index, scores: np.ndarray, k: int, min_score: float, expected=()) -> None:
    order = np.argsort(-scores)[:k]
    for rank, i in enumerate(order, 1):
        c = index.chunks[i]
        sec = c["metadata"].get("section", "?")
        mark = "✓" if sec in expected else " "
        below = "  (eşik altı)" if scores[i] < min_score else ""
        print(f"  {mark} {rank:>2}. {scores[i]:.4f}  {sec:<9} {short(c)}{below}")


def first_hit_rank(index: Index, scores: np.ndarray, expected: list[str]) -> int | None:
    """Beklenen bölümden gelen ilk chunk'ın sırası (1'den başlar); hiç yoksa None."""
    for rank, i in enumerate(np.argsort(-scores), 1):
        if index.chunks[i]["metadata"].get("section") in expected:
            return rank
    return None


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


def run_eval(index: Index, items: list[dict], k: int, min_score: float) -> int:
    sections = {c["metadata"].get("section") for c in index.chunks}
    unknown = [(it["id"], s) for it in items for s in it["expected"] if s not in sections]
    if unknown:
        print(f"Uyarı: indekste olmayan beklenen bölümler: {unknown}", file=sys.stderr)

    all_scores = index.search_many([it["question"] for it in items])
    in_scope, off_scope = [], []

    for it, scores in zip(items, all_scores):
        top = float(scores.max())
        label = it.get("difficulty", "")
        print(f"\n[{it['id']}] {it['question']}  ({label})")
        if it["expected"]:
            rank = first_hit_rank(index, scores, it["expected"])
            correct = max(float(scores[i]) for i, c in enumerate(index.chunks)
                          if c["metadata"].get("section") in it["expected"]) if rank else None
            status = f"doğru bölüm {rank}. sırada" if rank else "doğru bölüm yok"
            print(f"  beklenen: {', '.join(it['expected'])} → {status}")
            in_scope.append({"id": it["id"], "rank": rank, "top": top, "correct": correct})
        else:
            off_scope.append({"id": it["id"], "top": top})
        print_results(index, scores, k, min_score, it["expected"])

    # --- Özet ---
    print("\n" + "=" * 72)
    n = len(in_scope)
    if n:
        print(f"İlgili sorular: {n}")
        for h in HIT_AT:
            hits = sum(1 for r in in_scope if r["rank"] and r["rank"] <= h)
            print(f"  Hit@{h}: {hits}/{n}  ({hits / n:.0%})")
        mrr = sum(1 / r["rank"] for r in in_scope if r["rank"]) / n
        print(f"  MRR   : {mrr:.3f}")
        missed = [r["id"] for r in in_scope if not r["rank"] or r["rank"] > k]
        print(f"  İlk {k}'te olmayanlar: {', '.join(missed) if missed else 'yok'}")

        tops = [r["top"] for r in in_scope]
        corrects = [r["correct"] for r in in_scope if r["correct"] is not None]
        print(f"  En yüksek puan (her sorunun 1. sonucu): min {min(tops):.4f} / max {max(tops):.4f}")
        if corrects:
            print(f"  Doğru bölümün puanı              : min {min(corrects):.4f} / max {max(corrects):.4f}")

    if off_scope:
        offs = [r["top"] for r in off_scope]
        print(f"Konu dışı sorular: {len(off_scope)}")
        print(f"  En yüksek puan: min {min(offs):.4f} / max {max(offs):.4f}")
        if n:
            low_in = min(r["top"] for r in in_scope)
            high_off = max(offs)
            gap = low_in - high_off
            if gap > 0:
                print(f"  Ayrım VAR: ilgili sorular ≥ {low_in:.4f} > konu dışı ≤ {high_off:.4f} "
                      f"(boşluk {gap:.4f}) → minScore bu aralıktan seçilebilir.")
            else:
                print(f"  Ayrım YOK: konu dışı en yüksek {high_off:.4f} ≥ ilgili en düşük {low_in:.4f} "
                      f"→ tek bir minScore ikisini ayıramaz.")
    print(f"Ayarlar: topK={k}, minScore={min_score}")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
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
        provider = get_provider(project.get("embedding"))
        index = Index(project, provider)
        if args.eval:
            return run_eval(index, load_eval(project), k, min_score)
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1

    scores = index.search_many([args.question])[0]
    print(f"\n{args.question}")
    print_results(index, scores, k, min_score)
    return 0


if __name__ == "__main__":
    sys.exit(main())
