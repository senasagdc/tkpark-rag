"""Retrieval testi (LLM yok): belgede arama doğru bölümü buluyor mu?

Soru setindeki her soruyu rag/search.py'deki Retriever ile arar ve beklenen bölümün
kaçıncı sırada geldiğine bakar. Chatbot'un çalışması için gerekli değildir; yalnızca ölçüm.

Kullanım:
    python tests/retrieval_test.py
    python tests/retrieval_test.py --top 10 --project <id>
    python tests/retrieval_test.py --no-rewrite      # query rewriting kapalı (önce/sonra karşılaştırması)

Soru seti (proje klasörüne göre, yol project.json › eval.retrieval):
    eval/retrieval.jsonl, her satır:
    {"id": "q01", "question": "...", "expected": ["10.1"], "difficulty": "zor"}
    expected = doğru sayılan metadata.section değerleri. Boş liste = belgede cevabı olmayan soru;
    bunlar difficulty etiketine göre ("konu dışı", "cevapsız") ayrı gruplarda raporlanır.

Ölçümler:
    Hit@K  beklenen bölüm ilk K sonuçta mı (K = 1, 3, 5)
    MRR    1 / (beklenen bölümün sırası) ortalaması; 1.0 = hep 1. sırada
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rag"))

from config import ROOT, ConfigError, load_project  # noqa: E402
from search import Retriever, print_results  # noqa: E402

DEFAULT_EVAL_FILE = "eval/retrieval.jsonl"
HIT_AT = (1, 3, 5)


def load_questions(project) -> list[dict]:
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


def run(r: Retriever, items: list[dict], k: int, min_score: float) -> int:
    known = {c["metadata"].get("section") for c in r.chunks}
    unknown = [(it["id"], s) for it in items for s in it["expected"] if s not in known]
    if unknown:
        print(f"Uyarı: indekste olmayan beklenen bölümler: {unknown}", file=sys.stderr)

    all_scores, all_ids = r.search([it["question"] for it in items])
    answerable, unanswerable = [], []

    for it, scores, ids, rw in zip(items, all_scores, all_ids, r.last_rewrites):
        print(f"\n[{it['id']}] {it['question']}  ({it.get('difficulty', '')})")
        if rw:
            print(f"  yeniden yazıldı: {rw}")
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
    n_rw = sum(1 for rw in r.last_rewrites if rw)
    print(f"Ayarlar: topK={k}, minScore={min_score}, queryRewrite="
          + (f"açık ({n_rw}/{len(items)} soru yeniden yazıldı)" if r.rewriter else "kapalı"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval testi: arama doğru bölümü buluyor mu (LLM yok).")
    parser.add_argument("--top", type=int, help="gösterilecek sonuç sayısı (varsayılan: retrieval.topK)")
    parser.add_argument("--no-rewrite", action="store_true", help="query rewriting'i kapat")
    parser.add_argument("--project", help="projects/ altındaki proje klasörü (varsayılan: .env PROJECT)")
    args = parser.parse_args()
    try:
        project = load_project(args.project)
        k = args.top or int(project.get("retrieval.topK"))
        min_score = float(project.get("retrieval.minScore", 0.0))
        r = Retriever(project, rewrite=False if args.no_rewrite else None)
        return run(r, load_questions(project), k, min_score)
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
