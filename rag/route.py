"""Query routing (adım 5): soru retrieval'a girmeden önce bir rotaya ayrılır.

Rotalar:
    geçersiz   boş, çok kısa, çok uzun veya hiç harf içermeyen mesaj → kural, LLM'e gitmez
    sohbet     selam, teşekkür, "sen kimsin" → LLM kısa bir cevap yazar
    konu_dışı  belgeyle ilgisiz soru/istek → messages.json'daki sabit mesaj
    belge      normal RAG akışı (6 → 9)

Kullanım:
    python rag/route.py "Merhaba"                 # tek mesaj
    python rag/route.py --eval                    # routing test seti
    python rag/route.py --eval --project <id>

Ayarlar project.json'dan:
    routing.scope        belgenin kapsamı, tek cümle (routing prompt'una girer)
    routing.minChars     bundan kısa mesaj → geçersiz
    routing.maxChars     bundan uzun mesaj → geçersiz
    routing.temperature  (varsayılan 0.0)
    llm.model            Gemini modeli
    prompts.routing      prompt şablonu ({scope} ve prompts.vars değişkenleri)
    prompts.messages     sabit cevap metinleri ("geçersiz", "konu_dışı")
    eval.routing         test seti yolu (varsayılan: eval/routing.jsonl)

Test seti JSONL, her satır:
    {"id": "r01", "question": "...", "route": "belge", "note": "..."}

LLM hata verirse (ağ, zaman aşımı, bozuk cevap) soru "belge" sayılır: geçerli bir soruyu
reddetmek, ilgisiz bir soruyu RAG'e göndermekten daha kötü. Cevabı belgede yoksa
9. adımdaki "bilgim yok" kuralı yakalar.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time

from config import ROOT, ConfigError, load_project

LLM_ROUTES = ("belge", "sohbet", "konu_dışı")
ROUTES = ("geçersiz",) + LLM_ROUTES
FALLBACK_ROUTE = "belge"
DEFAULT_EVAL_FILE = "eval/routing.jsonl"
TIMEOUT_MS = 20_000
RETRIES = 3
MAX_WAIT_LIVE = 2.0    # canlı kullanımda kullanıcıyı en fazla bu kadar beklet, sonra fallback
MAX_WAIT_EVAL = 90.0   # eval'de kota (429) dolarsa önerilen süre kadar bekle

SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": list(LLM_ROUTES)},
        "reply": {"type": "string"},
    },
    "required": ["route", "reply"],
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


class Router:
    def __init__(self, project, max_wait: float = MAX_WAIT_LIVE):
        self.max_wait = max_wait
        self.min_chars = int(project.get("routing.minChars"))
        self.max_chars = int(project.get("routing.maxChars"))
        self.temperature = float(project.get("routing.temperature", 0.0))
        self.model = project.get("llm.model")

        values = {"scope": project.get("routing.scope"), **project.get("prompts.vars", {})}
        self.system = fill(read_file(project, "prompts.routing").read_text(encoding="utf-8"), values)

        messages = json.loads(read_file(project, "prompts.messages").read_text(encoding="utf-8"))
        for name in ("geçersiz", "konu_dışı"):
            if not messages.get(name):
                raise ConfigError(f"prompts.messages içinde '{name}' mesajı eksik.")
        self.messages = {k: fill(v, values) for k, v in messages.items()}

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ConfigError("GEMINI_API_KEY tanımlı değil (.env).")
        from google import genai  # yalnızca routing'de gerekiyor
        from google.genai import types
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        self.config = types.GenerateContentConfig(
            system_instruction=self.system,
            temperature=self.temperature,
            response_mime_type="application/json",
            response_json_schema=SCHEMA,
        )

    def check_rules(self, text: str) -> str | None:
        """Kural ihlali varsa sebebini döndürür, yoksa None."""
        if len(text) < self.min_chars:
            return f"{self.min_chars} karakterden kısa"
        if len(text) > self.max_chars:
            return f"{self.max_chars} karakterden uzun"
        if not any(c.isalpha() for c in text):
            return "harf içermiyor"
        return None

    def ask_llm(self, text: str) -> dict:
        """Geçici hatalarda (429 kota, 503 yoğunluk) tekrar dener; önerilen bekleme
        max_wait saniyeyi aşıyorsa beklemeden hatayı yükseltir (→ fallback).
        Beklenen süre self.waited'e yazılır (gecikme ölçümünden düşülür)."""
        self.waited = 0.0
        for attempt in range(RETRIES + 1):
            try:
                response = self.client.models.generate_content(model=self.model, contents=text, config=self.config)
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
        data = json.loads(response.text)
        if data.get("route") not in LLM_ROUTES:
            raise ValueError(f"beklenmeyen rota: {data.get('route')!r}")
        return data

    def route(self, question: str) -> dict:
        """→ {route, reply, source ('kural' | 'llm' | 'hata'), detail, ms}"""
        start = time.perf_counter()
        self.waited = 0.0
        text = (question or "").strip()

        reason = self.check_rules(text)
        if reason:
            result = {"route": "geçersiz", "reply": self.messages["geçersiz"], "source": "kural", "detail": reason}
        else:
            try:
                data = self.ask_llm(text)
                route = data["route"]
                if route == "sohbet":
                    reply = data.get("reply", "").strip() or None
                elif route == "konu_dışı":
                    reply = self.messages["konu_dışı"]
                else:
                    reply = None
                result = {"route": route, "reply": reply, "source": "llm", "detail": None}
            except Exception as e:  # ağ, zaman aşımı, bozuk JSON → soru reddedilmez
                result = {"route": FALLBACK_ROUTE, "reply": None, "source": "hata",
                          "detail": short(f"{type(e).__name__}: {e}", 160)}

        result["ms"] = (time.perf_counter() - start - self.waited) * 1000
        return result


def load_eval(project) -> list[dict]:
    path = project.path(project.get("eval.routing", DEFAULT_EVAL_FILE))
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
        if "question" not in item or item.get("route") not in ROUTES:
            raise ConfigError(f"{path.name}:{line_no}: 'question' ve 'route' ({'/'.join(ROUTES)}) zorunlu.")
        items.append(item)
    return items


def short(text: str, width: int = 60) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= width else text[: width - 1] + "…"


def run_eval(router: Router, items: list[dict]) -> int:
    results = []
    for it in items:
        r = router.route(it["question"])
        ok = r["route"] == it["route"]
        results.append((it, r))
        mark = "✓" if ok else "✗"
        print(f"{mark} [{it['id']}] {short(it['question']):<60}  beklenen {it['route']:<9} → {r['route']:<9}"
              f" ({r['source']}, {r['ms']:.0f} ms)")
        if r["source"] == "hata":
            print(f"    hata: {r['detail']}")
        elif r["route"] == "sohbet" and r["reply"]:
            print(f"    cevap: {short(r['reply'], 100)}")

    print("\n" + "=" * 72)
    n = len(results)
    correct = sum(1 for it, r in results if r["route"] == it["route"])
    print(f"Toplam doğruluk: {correct}/{n} ({correct / n:.0%})")

    print("\nRota başına (beklenen → doğru):")
    for route in ROUTES:
        rows = [(it, r) for it, r in results if it["route"] == route]
        if rows:
            hit = sum(1 for it, r in rows if r["route"] == route)
            print(f"  {route:<9}: {hit}/{len(rows)}")

    print("\nKarışıklık tablosu (satır = beklenen, sütun = çıkan):")
    print("  " + " " * 10 + "".join(f"{c:>11}" for c in ROUTES))
    for row in ROUTES:
        counts = [sum(1 for it, r in results if it["route"] == row and r["route"] == col) for col in ROUTES]
        if sum(counts):
            print(f"  {row:<10}" + "".join(f"{c:>11}" for c in counts))

    rejected = [it["id"] for it, r in results if it["route"] == "belge" and r["route"] != "belge"]
    print(f"\nYanlış reddedilen belge soruları: {', '.join(rejected) if rejected else 'yok'}")
    wrong = [f"{it['id']} ({it['route']} → {r['route']})" for it, r in results
             if r["route"] != it["route"] and it["route"] != "belge"]
    print(f"Diğer hatalı rotalar          : {', '.join(wrong) if wrong else 'yok'}")

    errors = [it["id"] for it, r in results if r["source"] == "hata"]
    if errors:
        print(f"UYARI: {len(errors)} soruda LLM hata verdi ve '{FALLBACK_ROUTE}' sayıldı: {', '.join(errors)}"
              " → sonuçlar güvenilir değil.")

    llm_ms = [r["ms"] for _, r in results if r["source"] == "llm"]
    if llm_ms:
        print(f"LLM gecikmesi: ort {statistics.mean(llm_ms):.0f} ms, medyan {statistics.median(llm_ms):.0f} ms,"
              f" en fazla {max(llm_ms):.0f} ms ({len(llm_ms)} çağrı)")
    print(f"Ayarlar: model={router.model}, temperature={router.temperature},"
          f" minChars={router.min_chars}, maxChars={router.max_chars}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Query routing (adım 5).")
    parser.add_argument("question", nargs="?", help="yönlendirilecek mesaj")
    parser.add_argument("--eval", action="store_true", help="routing test setini çalıştır")
    parser.add_argument("--project", help="projects/ altındaki proje klasörü (varsayılan: .env PROJECT)")
    args = parser.parse_args()
    if args.question is None and not args.eval:
        parser.error("bir mesaj ver ya da --eval kullan")

    try:
        project = load_project(args.project)
        router = Router(project, max_wait=MAX_WAIT_EVAL if args.eval else MAX_WAIT_LIVE)
        if args.eval:
            return run_eval(router, load_eval(project))
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1

    r = router.route(args.question)
    print(f"rota  : {r['route']}  ({r['source']}, {r['ms']:.0f} ms)")
    if r["detail"]:
        print(f"neden : {r['detail']}")
    if r["reply"]:
        print(f"cevap : {r['reply']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
