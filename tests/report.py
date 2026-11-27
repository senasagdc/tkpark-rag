"""Cevap testi raporu: tests/answer_test.py sonucundan Markdown rapor üretir (mentora göstermek için).

Kullanım:
    python tests/report.py                                 # eval/results/ içindeki en yeni sonuç
    python tests/report.py projects/yonerge/eval/results/cevaplar2.json
    python tests/report.py --compare <eski.json>           # önceki bir çalıştırmayla karşılaştır
    python tests/report.py --stdout                        # dosyaya yazmadan ekrana bas

Girdiler (proje klasörüne göre):
    eval/results/*.json          tests/answer_test.py çıktısı (soru, beklenen, çıkan, cevap, kaynaklar,
                                 LLM'e giden parçalar, gecikme, tekrar denemeler, ayarlar)
    eval/review.jsonl            elle inceleme notları (isteğe bağlı), her satır:
        {"id": "u02", "when_type": "cevap", "type_ok": true, "label_issue": true,
         "quality": "doğru" | "eksik" | "yanlış", "comment": "..."}
        when_type: notun yazıldığı sırada çıkan tür. Yeni çalıştırmada tür farklıysa not
        uygulanmaz ve "yeniden incele" diye işaretlenir (LLM her seferinde aynı cevabı vermez).
        type_ok: otomatik karşılaştırmayı geçersiz kılar (ör. etiket hatası).

Çıktı:
    eval/reports/<sonuç dosyasının adı>.md

Otomatik ölçümler cevap metninin doğruluğunu ölçmez; o yüzden "inceleme sonrası" sütunu ve
elle yazılan yorumlar ayrı tutulur. Ham sonuçlar her zaman raporda kalır.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rag"))

from config import ROOT, ConfigError, load_project  # noqa: E402

TYPES = ("geçersiz", "cevap", "bilgi_yok", "sohbet", "hata")
LLM_TYPES = ("cevap", "bilgi_yok", "sohbet")
DEFAULT_RESULTS_DIR = "eval/results"
DEFAULT_REPORTS_DIR = "eval/reports"
DEFAULT_REVIEW_FILE = "eval/review.jsonl"
# eski sonuç dosyalarında vectorStore yok: o zaman yalnızca FAISS vardı
STORE_LABELS = {"flat": "FAISS", "pgvector": "PostgreSQL + pgvector"}


def display(path: Path) -> str:
    """Proje kökü altındaysa göreli, değilse mutlak yol."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


# ---- okuma
def latest_result(project) -> Path:
    """Sonuç klasöründeki en yeni cevap testi sonucu (dosya adı ne olursa olsun, createdAt'e göre)."""
    folder = project.path(project.get("eval.resultsDir", DEFAULT_RESULTS_DIR))
    found = []
    for f in folder.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and data.get("kind") == "answer-eval":
            found.append((data.get("createdAt", ""), f))
    if not found:
        raise ConfigError(f"{display(folder)} içinde sonuç yok. Önce: python tests/answer_test.py")
    return max(found)[1]


def load_result(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Bulunamadı: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("kind") != "answer-eval":
        raise ConfigError(f"{path.name}: tests/answer_test.py sonucu değil.")
    return data


def load_review(project) -> dict[str, dict]:
    path = project.path(project.get("eval.review", DEFAULT_REVIEW_FILE))
    if not path.exists():
        return {}
    review = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ConfigError(f"{path.name}:{line_no}: geçersiz JSON ({e})") from e
            review[row["id"]] = row
    return review


# ---- hesap
def apply_review(rows: list[dict], review: dict[str, dict]) -> None:
    """Her satıra reviewed_ok, quality, comment, stale alanlarını ekler."""
    for r in rows:
        note = review.get(r["id"])
        r["reviewed_ok"], r["quality"], r["comment"], r["stale"], r["label_issue"] = r["type_ok"], None, None, False, False
        if not note:
            continue
        if note.get("when_type") and note["when_type"] != r["type"]:
            r["stale"] = True  # not başka bir sonuca göre yazılmış
            r["comment"] = f"(Not '{note['when_type']}' sonucu için yazılmıştı, bu çalıştırmada '{r['type']}' çıktı; yeniden incele.) {note.get('comment', '')}"
            continue
        if "type_ok" in note:
            r["reviewed_ok"] = bool(note["type_ok"])
        r["quality"] = note.get("quality")
        r["comment"] = note.get("comment")
        r["label_issue"] = bool(note.get("label_issue"))


def percentile(values: list[float], p: int) -> float:
    if len(values) < 2:
        return values[0] if values else 0.0
    return statistics.quantiles(values, n=100, method="inclusive")[p - 1]


def summarize(data: dict) -> dict:
    rows = data["results"]
    n = len(rows)
    llm = [r for r in rows if r["type"] in LLM_TYPES]
    ms = [r["ms"] for r in llm]
    src = [r for r in rows if r["source_ok"] is not None]
    retries = Counter(code for r in rows for code in r.get("retries", []))
    return {
        "n": n,
        "type_ok": sum(r["type_ok"] for r in rows),
        "reviewed_ok": sum(r["reviewed_ok"] for r in rows),
        "source_ok": (sum(r["source_ok"] for r in src), len(src)),
        "made_up": [r["id"] for r in rows if r["expect"] == "bilgi_yok" and r["type"] == "cevap"],
        "made_up_confirmed": [r["id"] for r in rows if r["expect"] == "bilgi_yok" and r["type"] == "cevap"
                              and not r["reviewed_ok"]],
        "refused": [r["id"] for r in rows if r["expect"] == "cevap" and r["type"] == "bilgi_yok"],
        "refused_confirmed": [r["id"] for r in rows if r["expect"] == "cevap" and r["type"] == "bilgi_yok"
                              and not r["reviewed_ok"]],
        "errors": [r["id"] for r in rows if r["type"] == "hata"],
        "incomplete": [r["id"] for r in rows if r.get("quality") in ("eksik", "yanlış")],
        "label_issues": [r["id"] for r in rows if r.get("label_issue")],
        "stale": [r["id"] for r in rows if r.get("stale")],
        "retries": retries,
        "waited": sum(r.get("waited_s", 0) for r in rows),
        "llm_calls": len(llm),
        "ms": {"mean": statistics.mean(ms), "median": statistics.median(ms),
               "p90": percentile(ms, 90), "max": max(ms)} if ms else None,
    }


# ---- Markdown yardımcıları
def cell(text) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def short(text: str, width: int) -> str:
    text = (text or "").replace("\n", " ")
    return text if len(text) <= width else text[: width - 1] + "…"


def table(header: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return out


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else "—"


def ids(items: list[str]) -> str:
    return ", ".join(items) if items else "yok"


def hit_rank(r: dict) -> int | None:
    for rank, h in enumerate(r["hits"], 1):
        if h["section"] in r["sections"]:
            return rank
    return None


def rank_stat(rows: list[dict], at: int | None) -> str:
    """Beklenen bölümü olan sorularda bölüm ilk `at` parçada mı (None = LLM'e giden parçaların herhangi birinde)."""
    g = [r for r in rows if r.get("sections")]
    ranks = [hit_rank(r) for r in g]
    return pct(sum(1 for x in ranks if x and (at is None or x <= at)), len(g))


# ---- rapor
def build_report(data: dict, result_path: Path, compare: dict | None) -> str:
    rows, s, st = data["results"], summarize(data), data["settings"]
    by_id = {r["id"]: r for r in rows}
    out = [f"# Cevap değerlendirme raporu — {data['project']}", ""]
    out += [f"- **Çalıştırma:** {data['createdAt']} · `{display(result_path)}`",
            f"- **Test seti:** `{data['testset']}`, {s['n']} soru" + ("" if data.get("complete", True) else " (kısmi çalıştırma)"),
            f"- **Ayarlar:** model `{st['model']}`, temperature {st['temperature']}, topK {st['topK']}, "
            f"embedding `{st['embedding']}`, system prompt `{st['systemPromptSha1']}`, query rewriting "
            + ("açık" if st.get("queryRewrite") else "kapalı"),
            f"- **Akış:** girdi kontrolü → retrieval ({STORE_LABELS.get(st.get('vectorStore', 'flat'), st.get('vectorStore'))}"
            ", ilk topK parça) → tek LLM çağrısı (JSON şeması: "
            "`cevap` / `bilgi_yok` / `sohbet` + kullanılan parça numaraları) → kaynaklar backend'de", ""]

    # özet
    out += ["## Özet", ""]
    summary_rows = [
        ["Tür doğruluğu (otomatik)", pct(s["type_ok"], s["n"])],
        ["Tür doğruluğu (elle inceleme sonrası)", pct(s["reviewed_ok"], s["n"])
         + (f" — etiket hatası: {ids(s['label_issues'])}" if s["label_issues"] else "")],
        ["Kaynak doğruluğu (beklenen bölüm gösterilen kaynaklarda)", pct(*s["source_ok"])],
        ["Uydurma şüphesi (bilgi_yok beklenirken cevap verdi)", f"otomatik: {ids(s['made_up'])} · "
                                                               f"incelemede doğrulanan: {ids(s['made_up_confirmed'])}"],
        ["Fazla temkin (cevap beklenirken bilgi_yok dedi)", f"otomatik: {ids(s['refused'])} · "
                                                            f"incelemede doğrulanan: {ids(s['refused_confirmed'])}"],
        ["Eksik / yanlış cevap (elle inceleme)", ids(s["incomplete"])],
        ["LLM hatası (cevap verilemedi)", ids(s["errors"])],
        ["Geçici API hatası, tekrar deneme", ", ".join(f"{k}: {v}" for k, v in sorted(s["retries"].items())) or "yok"],
    ]
    if s["ms"]:
        m = s["ms"]
        summary_rows.append(["Gecikme (retrieval + LLM, bekleme hariç)",
                             f"ort {m['mean']:.0f} ms · medyan {m['median']:.0f} · p90 {m['p90']:.0f} · "
                             f"en fazla {m['max']:.0f} ({s['llm_calls']} çağrı)"])
    out += table(["Ölçüm", "Sonuç"], summary_rows) + [""]
    if s["stale"]:
        out += [f"> ⚠ Şu soruların inceleme notu başka bir sonuca ait, yeniden incelenmeli: {ids(s['stale'])}", ""]

    # karşılaştırma
    if compare:
        c = summarize(compare)
        out += ["## Önceki çalıştırmayla karşılaştırma", "",
                f"Önceki: {compare['createdAt']}, system prompt `{compare['settings']['systemPromptSha1']}`", ""]
        out += table(["Ölçüm", "Önceki", "Bu"], [
            ["Tür doğruluğu (otomatik)", pct(c["type_ok"], c["n"]), pct(s["type_ok"], s["n"])],
            ["Kaynak doğruluğu", pct(*c["source_ok"]), pct(*s["source_ok"])],
            ["Retrieval: beklenen bölüm 1. sırada", *[rank_stat(x["results"], 1) for x in (compare, data)]],
            ["Retrieval: beklenen bölüm LLM'e giden parçalarda", *[rank_stat(x["results"], None) for x in (compare, data)]],
            ["Query rewriting", *["açık" if x["settings"].get("queryRewrite") else "kapalı" for x in (compare, data)]],
            ["Ortalama gecikme", f"{c['ms']['mean']:.0f} ms" if c["ms"] else "—",
             f"{s['ms']['mean']:.0f} ms" if s["ms"] else "—"],
        ]) + [""]
        old = {r["id"]: r for r in compare["results"]}
        changed = [[i, old[i]["type"], by_id[i]["type"], by_id[i]["expect"]] for i in by_id
                   if i in old and old[i]["type"] != by_id[i]["type"]]
        out += (table(["Soru", "Önceki tür", "Bu tür", "Beklenen"], changed) if changed
                else ["Türü değişen soru yok."]) + [""]

    # tür başına + karışıklık
    out += ["## Tür başına", ""]
    per = []
    for t in TYPES:
        g = [r for r in rows if r["expect"] == t]
        if g:
            per.append([t, len(g), sum(r["type_ok"] for r in g), sum(r["reviewed_ok"] for r in g)])
    out += table(["Beklenen tür", "Soru", "Doğru (otomatik)", "Doğru (inceleme sonrası)"], per) + [""]
    out += ["## Karışıklık tablosu", "", "Satır = beklenen, sütun = çıkan.", ""]
    used = [t for t in TYPES if any(r["expect"] == t or r["type"] == t for r in rows)]
    out += table(["beklenen \\ çıkan"] + used,
                 [[e] + [sum(1 for r in rows if r["expect"] == e and r["type"] == t) for t in used]
                  for e in used if any(r["expect"] == e for r in rows)]) + [""]

    # incelenecekler
    flagged = [r for r in rows if not r["type_ok"] or r.get("comment") or r["type"] == "hata"]
    out += ["## İncelenen / dikkat gereken sorular", ""]
    if not flagged:
        out += ["Yok.", ""]
    for r in flagged:
        verdict = "✓" if r["reviewed_ok"] else "✗"
        out += [f"### {r['id']} — {r['question'] or '(boş)'}", "",
                f"- **Beklenen → çıkan:** `{r['expect']}` → `{r['type']}` "
                f"(otomatik {'✓' if r['type_ok'] else '✗'}, inceleme sonrası {verdict})"]
        if r["answer"] and r["type"] in ("cevap", "sohbet"):
            out.append(f"- **Cevap:** {short(r['answer'], 400)}")
        if r["sources"]:
            out.append("- **Gösterilen kaynaklar:** " + ", ".join(f"{x['section']} (s. {', '.join(map(str, x.get('pages') or []))})"
                                                              for x in r["sources"]))
        if r["hits"]:
            out.append("- **LLM'e giden parçalar:** " + ", ".join(f"{h['id'] or h['section']} ({h['score']:.3f})" for h in r["hits"]))
        if r.get("detail"):
            out.append(f"- **Not:** {r['detail']}")
        if r.get("comment"):
            out.append(f"- **İnceleme:** {r['comment']}")
        out.append("")

    # retrieval
    answerable = [r for r in rows if r["sections"]]
    if answerable:
        out += ["## Retrieval: beklenen bölüm LLM'e giden parçaların kaçıncısı", ""]
        out += table(["Soru", "Beklenen", "Sıra", "1. parçanın puanı"],
                     [[r["id"], ", ".join(r["sections"]), hit_rank(r) or "yok",
                       f"{r['hits'][0]['score']:.3f}" if r["hits"] else "—"] for r in answerable]) + [""]
        ranks = [hit_rank(r) for r in answerable]
        out += [f"Beklenen bölüm 1. sırada: {sum(1 for x in ranks if x == 1)}/{len(ranks)}, "
                f"ilk {st['topK']} içinde: {sum(1 for x in ranks if x)}/{len(ranks)}.", ""]

    # gecikme
    if s["ms"]:
        buckets = [("< 1 sn", float("-inf"), 1000), ("1–2 sn", 1000, 2000), ("2–4 sn", 2000, 4000), ("≥ 4 sn", 4000, 1e12)]
        llm_ms = [r["ms"] for r in rows if r["type"] in LLM_TYPES]
        out += ["## Gecikme dağılımı", "", "Bekleme (429/503 sonrası tekrar deneme) süresi hariç.", ""]
        out += table(["Aralık", "Çağrı"], [[name, sum(1 for x in llm_ms if lo <= x < hi)] for name, lo, hi in buckets])
        out += ["", f"Toplam bekleme: {s['waited']:.0f} sn.", ""]

    # tüm sonuçlar
    out += ["## Tüm sonuçlar", ""]
    out += table(["Soru", "Beklenen", "Çıkan", "ms", "Kaynak", "Cevap"],
                 [[r["id"], r["expect"], r["type"] + ("" if r["type_ok"] else " ✗"), f"{r['ms']:.0f}",
                   ", ".join(x["section"] for x in r["sources"]), short(r["answer"] if r["type"] in ("cevap", "sohbet") else "", 140)]
                  for r in rows]) + [""]
    out += ["---", "Rapor `tests/report.py` ile üretildi. Otomatik ölçümler cevap metninin doğruluğunu ölçmez; "
            "elle inceleme notları `eval/review.jsonl` dosyasından gelir.", ""]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cevap testi sonucundan Markdown rapor üretir.")
    parser.add_argument("result", nargs="?", help="sonuç dosyası (varsayılan: en son eval/results/answer-*.json)")
    parser.add_argument("--compare", help="karşılaştırılacak önceki sonuç dosyası")
    parser.add_argument("--stdout", action="store_true", help="raporu dosyaya yazmadan ekrana bas")
    parser.add_argument("--project", help="projects/ altındaki proje klasörü (varsayılan: .env PROJECT)")
    args = parser.parse_args()
    try:
        project = load_project(args.project)
        path = Path(args.result).resolve() if args.result else latest_result(project)
        data = load_result(path)
        review = load_review(project)
        apply_review(data["results"], review)
        compare = None
        if args.compare:
            compare = load_result(Path(args.compare).resolve())
            apply_review(compare["results"], {})
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1

    report = build_report(data, path, compare)
    if args.stdout:
        print(report)
        return 0
    out_dir = project.path(project.get("eval.reportsDir", DEFAULT_REPORTS_DIR))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (path.stem + ".md")
    out.write_text(report, encoding="utf-8")
    print(f"Rapor yazıldı: {display(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
