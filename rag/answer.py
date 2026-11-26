"""Uçtan uca cevap (adım 9 + LLM): girdi kontrolü → retrieval → prompt → Gemini → cevap + kaynaklar.

Ayrı bir routing adımı yok (26.11 kararı). Sohbet, konu dışı ve "bilgim yok" kararını
cevabı üreten LLM, kendisine verilen belge parçalarına bakarak verir (prompts/system.md).

Cevap türleri:
    geçersiz   boş, çok kısa, çok uzun veya harfsiz mesaj → kural, LLM'e gitmez
    cevap      cevap belge parçalarında var → LLM'in cevabı + kaynaklar
    bilgi_yok  cevap parçalarda yok veya mesaj konu dışı → messages.json'daki sabit metin
    sohbet     selam, teşekkür, "sen kimsin" → LLM'in kısa cevabı
    hata       LLM'e ulaşılamadı → messages.json'daki hata metni

Kullanım:
    python rag/answer.py "Firma kabul şartları nelerdir?"
    python rag/answer.py --eval                    # eval/testset.jsonl → eval/results/answer-<zaman>.json
    python rag/answer.py --eval --only q01,s01     # yalnızca bu id'ler
    python rag/answer.py --eval --no-save          # sonucu dosyaya yazma
    python rag/answer.py "soru" --dry-run          # LLM'e gitmeden prompt'u yazdır

--eval sonucu JSON olarak kaydedilir; rapor için: python rag/analyze.py

Ayarlar project.json'dan:
    input.minChars / input.maxChars   girdi kontrolü sınırları
    retrieval.topK                    LLM'e verilen parça sayısı
    llm.model, llm.temperature
    prompts.system                    sistem prompt'u ({organization}, {assistantName} ... prompts.vars'tan)
    prompts.messages                  "geçersiz", "bilgi_yok", "hata" sabit metinleri
    eval.testset                      test seti (varsayılan: eval/testset.jsonl)
    eval.resultsDir                   sonuç klasörü (varsayılan: eval/results)

Kaynaklar backend'de üretilir: LLM yalnızca kullandığı parçaların numarasını döndürür,
bölüm / başlık / sayfa bilgisi retrieval'ın getirdiği chunk'ların metadata'sından gelir.
Böylece LLM var olmayan bir kaynak uyduramaz.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime

from config import ROOT, ConfigError, load_project

TYPES = ("geçersiz", "cevap", "bilgi_yok", "sohbet", "hata")
LLM_TYPES = ("cevap", "bilgi_yok", "sohbet")
DEFAULT_EVAL_FILE = "eval/testset.jsonl"
DEFAULT_RESULTS_DIR = "eval/results"
TIMEOUT_MS = 30_000
RETRIES = 3
MAX_WAIT_LIVE = 2.0    # canlı kullanımda kota dolarsa en fazla bu kadar bekle
MAX_WAIT_EVAL = 90.0   # eval'de Google'ın önerdiği süre kadar bekle

SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": list(LLM_TYPES)},
        "answer": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["type", "answer", "sources"],
}


def fill(template: str, values: dict) -> str:
    """{ad} yer tutucularını doldurur. Bilinmeyen yer tutucu varsa hata verir."""
    missing = set(re.findall(r"\{(\w+)\}", template)) - values.keys()
    if missing:
        raise ConfigError(f"Şablonda tanımsız değişken(ler): {sorted(missing)}")
    return re.sub(r"\{(\w+)\}", lambda m: str(values[m.group(1)]), template)


def read_file(project, key: str):
    path = project.path(project.get(key))
    if not path.exists():
        raise ConfigError(f"Bulunamadı: {path.relative_to(ROOT)} ({key})")
    return path


def pages_label(pages) -> str:
    if not pages:
        return ""
    return f"s. {pages[0]}" if len(pages) == 1 else f"s. {pages[0]}–{pages[-1]}"


def short(text: str, width: int = 60) -> str:
    text = (text or "").replace("\n", " ")
    return text if len(text) <= width else text[: width - 1] + "…"


class Assistant:
    def __init__(self, project, max_wait: float = MAX_WAIT_LIVE, dry_run: bool = False):
        self.max_wait = max_wait
        self.dry_run = dry_run
        self.min_chars = int(project.get("input.minChars"))
        self.max_chars = int(project.get("input.maxChars"))
        self.top_k = int(project.get("retrieval.topK"))
        self.model_name = project.get("llm.model")
        self.temperature = float(project.get("llm.temperature", 0.1))
        self.embedding_model = project.get("embedding.model")
        self.project = project

        values = dict(project.get("prompts.vars", {}))
        self.system = fill(read_file(project, "prompts.system").read_text(encoding="utf-8"), values)
        messages = json.loads(read_file(project, "prompts.messages").read_text(encoding="utf-8"))
        for name in ("geçersiz", "bilgi_yok", "hata"):
            if not messages.get(name):
                raise ConfigError(f"prompts.messages içinde '{name}' mesajı eksik.")
        self.messages = {k: fill(v, values) for k, v in messages.items()}

        from search import Retriever  # embedding modeli yükleniyor (birkaç saniye)
        self.retriever = Retriever(project)

        self.client = None
        if not dry_run:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise ConfigError("GEMINI_API_KEY tanımlı değil (.env). Prompt'u görmek için --dry-run kullan.")
            from google import genai
            from google.genai import types
            self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
            self.config = types.GenerateContentConfig(
                system_instruction=self.system,
                temperature=self.temperature,
                response_mime_type="application/json",
                response_json_schema=SCHEMA,
            )

    # ---- adımlar
    def check_input(self, text: str) -> str | None:
        """Kural ihlali varsa sebebini döndürür, yoksa None."""
        if len(text) < self.min_chars:
            return f"{self.min_chars} karakterden kısa"
        if len(text) > self.max_chars:
            return f"{self.max_chars} karakterden uzun"
        if not any(c.isalpha() for c in text):
            return "harf içermiyor"
        return None

    def retrieve(self, text: str) -> list[dict]:
        scores, ids = self.retriever.search([text])
        hits = []
        for s, i in zip(scores[0][: self.top_k], ids[0][: self.top_k]):
            c = self.retriever.chunks[int(i)]
            hits.append({"score": float(s), "id": c["id"], "text": c["text"], **c["metadata"]})
        return hits

    def build_prompt(self, text: str, hits: list[dict]) -> str:
        parts = ["BELGE PARÇALARI:"]
        for n, h in enumerate(hits, 1):
            label = " · ".join(x for x in (f"Bölüm {h.get('section', '?')}", pages_label(h.get("pages"))) if x)
            parts.append(f"[{n}] ({label})\n{h['text']}")
        parts.append(f"KULLANICI MESAJI:\n{text}")
        return "\n\n".join(parts)

    def ask_llm(self, prompt: str) -> dict:
        """429 / 503'te tekrar dener; önerilen bekleme max_wait'i aşarsa hatayı yükseltir."""
        self.waited = 0.0
        self.retries = []
        for attempt in range(RETRIES + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name, contents=prompt, config=self.config)
                break
            except Exception as e:
                code = getattr(e, "code", None)
                if code not in (429, 503) or attempt == RETRIES:
                    raise
                m = re.search(r"retry in ([\d.]+)s", str(e))
                wait = float(m.group(1)) + 1 if m else 2.0 * (attempt + 1)
                if wait > self.max_wait:
                    raise
                print(f"    ({code}, {wait:.0f} sn bekleyip tekrar deneniyor)", file=sys.stderr)
                time.sleep(wait)
                self.waited += wait
                self.retries.append(code)
        data = json.loads(response.text)
        if data.get("type") not in LLM_TYPES:
            raise ValueError(f"beklenmeyen tür: {data.get('type')!r}")
        return data

    def sources_from(self, numbers, hits: list[dict]) -> list[dict]:
        """LLM'in verdiği parça numaralarını chunk metadata'sına çevirir (geçersiz numaralar atılır,
        aynı bölüm bir kez gösterilir)."""
        out, seen = [], set()
        for n in numbers or []:
            if isinstance(n, int) and 1 <= n <= len(hits):
                h = hits[n - 1]
                key = h.get("section")
                if key in seen:
                    continue
                seen.add(key)
                out.append({"section": h.get("section"), "title": h.get("title"), "pages": h.get("pages"),
                            "source": h.get("source")})
        return out

    # ---- ana akış
    def answer(self, question: str) -> dict:
        """→ {type, answer, sources, hits, detail, ms}"""
        start = time.perf_counter()
        self.waited = 0.0
        self.retries = []
        text = (question or "").strip()
        result = {"type": None, "answer": None, "sources": [], "hits": [], "detail": None}

        reason = self.check_input(text)
        if reason:
            result.update(type="geçersiz", answer=self.messages["geçersiz"], detail=reason)
        else:
            hits = self.retrieve(text)
            result["hits"] = hits
            prompt = self.build_prompt(text, hits)
            if self.dry_run:
                result.update(type="dry_run", answer=prompt)
            else:
                try:
                    data = self.ask_llm(prompt)
                    kind = data["type"]
                    if kind == "bilgi_yok":
                        result.update(type=kind, answer=self.messages["bilgi_yok"])
                    elif kind == "sohbet":
                        result.update(type=kind, answer=data.get("answer", "").strip())
                    else:
                        sources = self.sources_from(data.get("sources"), hits)
                        if not sources:  # LLM numara vermediyse getirilen parçaları göster
                            sources = self.sources_from(range(1, len(hits) + 1), hits)
                            result["detail"] = "LLM kaynak numarası vermedi; getirilen tüm parçalar gösteriliyor"
                        result.update(type=kind, answer=data.get("answer", "").strip(), sources=sources)
                        if not result["answer"]:
                            result.update(type="bilgi_yok", answer=self.messages["bilgi_yok"],
                                          sources=[], detail="LLM 'cevap' dedi ama metin boş")
                except Exception as e:
                    result.update(type="hata", answer=self.messages["hata"],
                                  detail=short(f"{type(e).__name__}: {e}", 200))

        result["ms"] = (time.perf_counter() - start - self.waited) * 1000
        result["waited_s"] = self.waited
        result["retries"] = list(self.retries)
        return result

    def settings(self) -> dict:
        return {"model": self.model_name, "temperature": self.temperature, "topK": self.top_k,
                "minChars": self.min_chars, "maxChars": self.max_chars,
                "embedding": self.embedding_model,
                "systemPromptSha1": hashlib.sha1(self.system.encode("utf-8")).hexdigest()[:12]}


def format_sources(sources: list[dict]) -> list[str]:
    return [f"  • {s['section']} {s.get('title') or ''} ({pages_label(s.get('pages'))})".rstrip()
            for s in sources]


# ---- test seti
def load_eval(project) -> list[dict]:
    path = project.path(project.get("eval.testset", DEFAULT_EVAL_FILE))
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


def save_results(a: Assistant, items: list[dict], results: list) -> str:
    """--eval sonucunu analyze.py'nin okuyacağı JSON olarak kaydeder."""
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
            "testset": a.project.get("eval.testset", DEFAULT_EVAL_FILE), "complete": len(items) == len(load_eval(a.project)),
            "settings": a.settings(), "results": rows}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return display(path)


def display(path) -> str:
    """Proje kökü altındaysa göreli, değilse mutlak yol."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def run_eval(a: Assistant, items: list[dict], save: bool = True) -> int:
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
        print(f"\nSonuç kaydedildi: {save_results(a, items, results)}")
        print("Rapor için: python rag/analyze.py")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Uçtan uca cevap (retrieval + LLM).")
    parser.add_argument("question", nargs="?", help="soru")
    parser.add_argument("--eval", action="store_true", help="test setini çalıştır")
    parser.add_argument("--only", help="--eval'de yalnızca bu id'ler (virgülle)")
    parser.add_argument("--dry-run", action="store_true", help="LLM'e gitme, prompt'u yazdır")
    parser.add_argument("--no-save", action="store_true", help="--eval sonucunu dosyaya kaydetme")
    parser.add_argument("--project", help="projects/ altındaki proje klasörü (varsayılan: .env PROJECT)")
    args = parser.parse_args()
    if args.question is None and not args.eval:
        parser.error("bir soru ver ya da --eval kullan")
    if args.eval and args.dry_run:
        parser.error("--dry-run yalnızca tek soruyla kullanılır")

    try:
        project = load_project(args.project)
        a = Assistant(project, max_wait=MAX_WAIT_EVAL if args.eval else MAX_WAIT_LIVE, dry_run=args.dry_run)
        if args.eval:
            items = load_eval(project)
            if args.only:
                wanted = set(args.only.split(","))
                items = [it for it in items if it["id"] in wanted]
            return run_eval(a, items, save=not args.no_save)
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1

    r = a.answer(args.question)
    if r["type"] == "dry_run":
        print("=== SİSTEM PROMPT'U ===\n" + a.system + "\n=== KULLANICI İÇERİĞİ ===\n" + r["answer"])
        return 0
    print(f"tür   : {r['type']}  ({r['ms']:.0f} ms)")
    if r["detail"]:
        print(f"not   : {r['detail']}")
    print(f"\n{r['answer']}")
    if r["sources"]:
        print("\nKaynaklar:")
        print("\n".join(format_sources(r["sources"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
