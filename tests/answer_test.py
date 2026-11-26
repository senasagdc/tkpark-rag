"""Cevap testi (LLM var): chatbot test setindeki sorulara doğru türde ve doğru kaynakla cevap veriyor mu?

Test setindeki her soruyu rag/answer.py'deki Assistant'a sorar, çıkan türü (cevap / bilgi_yok /
sohbet / geçersiz) beklenen türle, gösterilen kaynağı beklenen bölümle karşılaştırır.
Sonucu JSON olarak kaydeder; rapor için: python tests/report.py
Chatbot'un çalışması için gerekli değildir; yalnızca ölçüm.

Kullanım:
    python tests/answer_test.py                       # tüm test seti
    python tests/answer_test.py --only q01,s01        # yalnızca bu id'ler
    python tests/answer_test.py --no-save             # sonucu dosyaya yazma

Dosyalar (proje klasörüne göre):
    eval/testset.jsonl   test seti (yol project.json › eval.testset), her satır:
        {"id": "q01", "question": "...", "expect": "cevap", "sections": ["10.1"], "note": "..."}
        expect: geçersiz / cevap / bilgi_yok / sohbet
        sections: yalnızca kaynak kontrolü yapılacak cevap sorularında
    eval/results/answer-<zaman>.json   sonuç (klasör project.json › eval.resultsDir)

Ölçümler:
    Tür doğruluğu     çıkan tür = beklenen tür
    Kaynak doğruluğu  beklenen bölüm gösterilen kaynaklarda mı
    Uydurma riski     bilgi_yok beklenirken cevap verdi
    Fazla temkin      cevap beklenirken bilgi_yok dedi
Cevap metninin doğruluğunu otomatik ölçmez; onu elle okuyup eval/review.jsonl'a not düşeriz.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rag"))

from answer import LLM_TYPES, TYPES, Assistant, short  # noqa: E402
from config import ROOT, ConfigError, load_project  # noqa: E402

DEFAULT_TESTSET = "eval/testset.jsonl"
DEFAULT_RESULTS_DIR = "eval/results"
MAX_WAIT = 90.0   # testte kota dolarsa Google'ın önerdiği süre kadar bekle (canlıda ~2 sn)


def display(path: Path) -> str:
    """Proje kökü altındaysa göreli, değilse mutlak yol."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_testset(project) -> list[dict]:
    path = project.path(project.get("eval.testset", DEFAULT_TESTSET))
    if not path.exists():
        raise ConfigError(f"Test seti bulunamadı: {path.relative_to(ROOT)}")
    items = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as e:
            raise ConfigError(f"{path.name}:{line_no}: geçersiz JSON ({e})") from e
        if "question" not in item or item.get("expect") not in TYPES:
            raise ConfigError(f"{path.name}:{line_no}: 'question' ve 'expect' ({'/'.join(TYPES)}) zorunlu.")
        items.append(item)
    return items


def save_results(a: Assistant, items: list[dict], results: list, complete: bool) -> str:
    """Sonucu report.py'nin okuyacağı JSON olarak kaydeder."""
    started = datetime.now()
    out_dir = a.project.path(a.project.get("eval.resultsDir", DEFAULT_RESULTS_DIR))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"answer-{started:%Y%m%d-%H%M%S}.json"
    rows = []
    for it, r, ok, src_ok in results:
        rows.append({
            "id": it["id"], "question": it["question"], "expect": it["expect"],
            "sections": it.get("sections", []), "note": it.get("note"),
            "type": r["type"], "type_ok": ok, "source_ok": src_ok,
            "answer": r["answer"], "sources": r["sources"], "detail": r["detail"],
            "hits": [{"id": h.get("id"), "section": h.get("section"), "score": round(h["score"], 4),
                      "pages": h.get("pages")} for h in r["hits"]],
            "ms": round(r["ms"], 1), "waited_s": r.get("waited_s", 0.0), "retries": r.get("retries", []),
        })
    data = {"kind": "answer-eval", "project": a.project.id, "createdAt": started.isoformat(timespec="seconds"),
            "testset": a.project.get("eval.testset", DEFAULT_TESTSET), "complete": complete,
            "settings": a.settings(), "results": rows}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return display(path)


def run(a: Assistant, items: list[dict], save: bool = True, complete: bool = True) -> int:
    results = []
    for it in items:
        r = a.answer(it["question"])
        ok = r["type"] == it["expect"]
        src_ok = None
        if it.get("sections") and r["type"] == "cevap":
            src_ok = any(s["section"] in it["sections"] for s in r["sources"])
        results.append((it, r, ok, src_ok))

        mark = "✓" if ok else "✗"
        src = "" if src_ok is None else ("  kaynak ✓" if src_ok else "  kaynak ✗")
        print(f"{mark} [{it['id']}] {short(it['question']):<55} beklenen {it['expect']:<9} → {r['type']:<9}"
              f" ({r['ms']:.0f} ms){src}")
        if r["type"] in ("cevap", "sohbet"):
            print(f"    cevap : {short(r['answer'], 160)}")
        if r["sources"]:
            print(f"    kaynak: {', '.join(s['section'] for s in r['sources'])}"
                  + (f"  (beklenen {', '.join(it['sections'])})" if it.get("sections") else ""))
        if r["detail"] and r["type"] != "geçersiz":
            print(f"    not   : {r['detail']}")

    print("\n" + "=" * 72)
    n = len(results)
    correct = sum(1 for *_, ok, _ in results if ok)
    print(f"Tür doğruluğu: {correct}/{n} ({correct / n:.0%})")
    print("\nTür başına (beklenen → doğru):")
    for t in TYPES:
        rows = [x for x in results if x[0]["expect"] == t]
        if rows:
            print(f"  {t:<9}: {sum(1 for x in rows if x[2])}/{len(rows)}")

    print("\nKarışıklık tablosu (satır = beklenen, sütun = çıkan):")
    print("  " + " " * 10 + "".join(f"{c:>11}" for c in TYPES))
    for row in TYPES:
        counts = [sum(1 for it, r, *_ in results if it["expect"] == row and r["type"] == col) for col in TYPES]
        if sum(counts):
            print(f"  {row:<10}" + "".join(f"{c:>11}" for c in counts))

    with_src = [x for x in results if x[3] is not None]
    if with_src:
        print(f"\nKaynak doğruluğu (beklenen bölüm gösterilen kaynaklarda): "
              f"{sum(1 for x in with_src if x[3])}/{len(with_src)}")
    made_up = [it["id"] for it, r, *_ in results if it["expect"] == "bilgi_yok" and r["type"] == "cevap"]
    refused = [it["id"] for it, r, *_ in results if it["expect"] == "cevap" and r["type"] == "bilgi_yok"]
    print(f"Uydurma riski (bilgi_yok beklenirken cevap verdi): {', '.join(made_up) or 'yok'}")
    print(f"Fazla temkin (cevap beklenirken bilgi_yok dedi)   : {', '.join(refused) or 'yok'}")
    errors = [it["id"] for it, r, *_ in results if r["type"] == "hata"]
    if errors:
        print(f"UYARI: {len(errors)} soruda LLM hata verdi: {', '.join(errors)} → sonuçlar güvenilir değil.")
    llm_ms = [r["ms"] for _, r, *_ in results if r["type"] in LLM_TYPES]
    if llm_ms:
        print(f"Gecikme (retrieval + LLM): ort {statistics.mean(llm_ms):.0f} ms, medyan {statistics.median(llm_ms):.0f} ms,"
              f" en fazla {max(llm_ms):.0f} ms ({len(llm_ms)} çağrı)")
    print(f"Ayarlar: model={a.model_name}, temperature={a.temperature}, topK={a.top_k},"
          f" minChars={a.min_chars}, maxChars={a.max_chars}")
    if save:
        print(f"\nSonuç kaydedildi: {save_results(a, items, results, complete)}")
        print("Rapor için: python tests/report.py")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Cevap testi: chatbot test setine doğru cevap veriyor mu (LLM var).")
    parser.add_argument("--only", help="yalnızca bu id'ler (virgülle)")
    parser.add_argument("--no-save", action="store_true", help="sonucu dosyaya kaydetme")
    parser.add_argument("--project", help="projects/ altındaki proje klasörü (varsayılan: .env PROJECT)")
    args = parser.parse_args()
    try:
        project = load_project(args.project)
        items = load_testset(project)
        total = len(items)
        if args.only:
            wanted = set(args.only.split(","))
            items = [it for it in items if it["id"] in wanted]
        a = Assistant(project, max_wait=MAX_WAIT)
        return run(a, items, save=not args.no_save, complete=len(items) == total)
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
