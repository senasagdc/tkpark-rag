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
    python rag/answer.py "soru" --dry-run          # LLM'e gitmeden prompt'u yazdır

Test seti ve ölçüm burada değil: python tests/answer_test.py (bkz. tests/README.md)

Ayarlar project.json'dan:
    input.minChars / input.maxChars   girdi kontrolü sınırları
    retrieval.topK                    LLM'e verilen parça sayısı
    llm.model, llm.temperature
    prompts.system                    sistem prompt'u ({organization}, {assistantName} ... prompts.vars'tan)
    prompts.messages                  "geçersiz", "bilgi_yok", "hata" sabit metinleri

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
import sys
import time

from config import ROOT, ConfigError, load_project

TYPES = ("geçersiz", "cevap", "bilgi_yok", "sohbet", "hata")
LLM_TYPES = ("cevap", "bilgi_yok", "sohbet")
TIMEOUT_MS = 30_000
RETRIES = 3
MAX_WAIT_LIVE = 2.0    # canlı kullanımda kota dolarsa en fazla bu kadar bekle (testte: tests/answer_test.py)

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


def main() -> int:
    parser = argparse.ArgumentParser(description="Uçtan uca cevap (retrieval + LLM).")
    parser.add_argument("question", help="soru")
    parser.add_argument("--dry-run", action="store_true", help="LLM'e gitme, prompt'u yazdır")
    parser.add_argument("--project", help="projects/ altındaki proje klasörü (varsayılan: .env PROJECT)")
    args = parser.parse_args()

    try:
        project = load_project(args.project)
        a = Assistant(project, dry_run=args.dry_run)
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
