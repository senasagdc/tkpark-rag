"""pages.json → temizlik + yapı tespiti + chunking → index/<proje-id>/chunks.json

Kullanım:
    python rag/chunk.py                 # .env › PROJECT
    python rag/chunk.py --project <id>

Ayarlar project.json › chunking:
  strategy        "heading" | "fixed"
  headingPatterns üst seviyeden alta regex listesi (1. eleman = 1. seviye). Eşleşen kısım
                  bölüm numarasıdır (ör. "7.1.5."); kalan metin başlıktır.
  bullet          madde işareti (ör. "•"); uzun bölümler önce bu sınırlardan bölünür
  maxTokens       bir chunk'ın en fazla token sayısı (bölüm başlık yolu dahil)
  overlap         aynı bölümün ardışık parçaları arasındaki örtüşme (token)
  fallback        heading stratejisi hiç başlık bulamazsa: {"strategy": "fixed", "maxTokens", "overlap"}
  tokenizer       (isteğe bağlı) token sayımı için Hugging Face modeli; varsayılan embedding.model
  strategy=fixed  için: maxTokens, overlap

Boyut, embedding modelinin kendi tokenizer'ıyla ölçülür; böylece modelin token sınırı
doğrudan kontrol edilir. Sayım, sağlayıcıya özel önekler ("passage: ") ve özel tokenlar
olmadan yapılır; bunlar için maxTokens model sınırının altında tutulmalıdır.

İlke: bölüm sınırı asla aşılmaz. Uzun bölüm yalnızca kendi içinde bölünür ve her parçanın
başına bölümün başlık yolu ("7. … > 7.1.5. …") eklenir.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import ROOT, ConfigError, cli_project

SCHEMA_VERSION = 1
TITLE_MAX_CHARS = 150        # bundan uzun "başlık" aslında gövde metnidir
TITLE_UPPER_RATIO = 0.7      # numara tek başına satırdaysa, alttaki satır büyük harfliyse başlıktır
MIN_BODY_TOKENS = 50         # başlık yolu yer kaplasa da her parçada en az bu kadar gövde kalmalı
LABEL_RE = re.compile(r"^[^:]{1,60}:\s")  # "Terim: tanım" satırı → yeni blok

Counter = Callable[[str], int]


def make_token_counter(model: str) -> Counter:
    """Embedding modelinin tokenizer'ıyla token sayar (özel tokenlar hariç)."""
    from transformers import AutoTokenizer
    from transformers.utils import logging as hf_logging

    hf_logging.set_verbosity_error()  # uzun gövdeleri saymak için 512 uyarısını sustur
    try:
        tok = AutoTokenizer.from_pretrained(model)
    except Exception as e:
        raise ConfigError(f"Tokenizer yüklenemedi ({model}): {e}") from e
    return lambda text: len(tok.encode(text, add_special_tokens=False))


# ---------------------------------------------------------------- temizlik

@dataclass
class Line:
    text: str
    page: int


@dataclass
class Block:
    """PDF satır sonları birleştirilmiş tek paragraf veya madde."""
    text: str
    pages: set[int] = field(default_factory=set)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def read_lines(pages: list[dict]) -> list[Line | None]:
    """Sayfaları satırlara açar. Boş satır → None (paragraf sınırı ipucu)."""
    out: list[Line | None] = []
    for p in pages:
        for raw in p["text"].splitlines():
            text = normalize(raw)
            out.append(Line(text, p["page"]) if text else None)
    return out


def to_blocks(lines: list[Line | None], bullet: str | None) -> list[Block]:
    """PDF satırlarını paragraf/madde bloklarına birleştirir."""
    blocks: list[Block] = []
    new_block = True
    for line in lines:
        if line is None:
            new_block = True
            continue
        t = line.text
        starts_new = (
            new_block
            or not blocks
            or (bullet and t.startswith(bullet))
            or (t[0].isupper() and LABEL_RE.match(t))
        )
        if starts_new:
            blocks.append(Block(t, {line.page}))
        else:
            prev = blocks[-1]
            prev.text += ("" if prev.text.endswith("-") else " ") + t
            prev.pages.add(line.page)
        new_block = t.endswith((".", ":", ";", "!", "?"))
    return blocks


# ---------------------------------------------------------------- yapı tespiti

@dataclass
class Section:
    id: str | None           # "7.1.5", "7.2.2.a"; başlıktan önceki metin için None
    label: str               # belgede yazdığı gibi: "7.1.5.", "a."
    level: int
    title: str
    parents: list["Section"]
    lines: list[Line | None] = field(default_factory=list)

    @property
    def heading(self) -> str:
        return f"{self.label} {self.title}".strip()

    @property
    def path(self) -> list[str]:
        return [s.heading for s in self.parents] + [self.heading]


def is_title_like(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters or len(text) > TITLE_MAX_CHARS:
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= TITLE_UPPER_RATIO


def split_heading(rest: str) -> tuple[str, str | None]:
    """Numaradan sonra kalan metin → (başlık, gövdeye kalan metin)."""
    if len(rest) <= TITLE_MAX_CHARS and not rest.endswith((".", ";", ",")):
        return rest, None
    return "", rest  # "12.3. Girişimci … yükümlüdür." gibi numaralı kural: başlık yok


def match_heading(line: Line | None, patterns: list[re.Pattern]) -> tuple[int, str, str] | None:
    """→ (seviye, numara, numaradan sonra kalan metin) veya None."""
    if line is None:
        return None
    for level, rx in enumerate(patterns, 1):
        if m := rx.match(line.text):
            return level, m.group(0).strip(), line.text[m.end():].strip()
    return None


def detect_sections(lines: list[Line | None], patterns: list[re.Pattern], doc_title: str) -> list[Section]:
    preamble = Section(None, "", 0, doc_title, [])
    sections = [preamble]
    stack: dict[int, Section] = {}

    def next_text_index(j: int) -> int:
        while j < len(lines) and lines[j] is None:
            j += 1
        return j

    def is_title_line(j: int) -> bool:
        return j < len(lines) and is_title_like(lines[j].text) and not match_heading(lines[j], patterns)

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        match = match_heading(line, patterns)
        if not match:
            sections[-1].lines.append(line)
            continue

        level, label, rest = match
        body_start = None
        if rest:
            title, body_start = split_heading(rest)
        else:
            # Numara tek başına satırda ("10.1."): alttaki satır büyük harfliyse başlıktır.
            j = next_text_index(i)
            title = ""
            if is_title_line(j):
                title, i = lines[j].text, j + 1
        # Büyük harfli başlık alt satıra taşmışsa ("… ALANIN" / "BOŞALTILMASI") birleştir.
        while title and not body_start and is_title_like(title):
            j = next_text_index(i)
            if not is_title_line(j) or len(title) + len(lines[j].text) > TITLE_MAX_CHARS:
                break
            title, i = f"{title} {lines[j].text}", j + 1

        parents = [stack[lv] for lv in sorted(stack) if lv < level]
        raw_id = label.rstrip(".")
        parent = parents[-1] if parents else None
        sec_id = raw_id if not parent or raw_id.startswith(parent.id + ".") else f"{parent.id}.{raw_id}"

        sec = Section(sec_id, label, level, title, parents)
        if body_start:
            sec.lines.append(Line(body_start, line.page))
        sections.append(sec)
        stack = {lv: s for lv, s in stack.items() if lv < level}
        stack[level] = sec
    return sections


# ---------------------------------------------------------------- chunking

def make_splitter(size: int, overlap: int, bullet: str | None, count: Counter) -> RecursiveCharacterTextSplitter:
    separators = [r"\n", r"(?<=[.;:!?])\s+", r"\s+", ""]
    if bullet:
        separators.insert(0, rf"\n(?={re.escape(bullet)})")
    return RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        length_function=count,
        separators=separators,
        is_separator_regex=True,
        keep_separator="start",
        add_start_index=True,
    )


def join_blocks(blocks: list[Block]) -> tuple[str, list[tuple[int, int, set[int]]]]:
    """Blokları '\\n' ile birleştirir; her bloğun [başlangıç, bitiş) aralığı ve sayfaları."""
    spans, parts, pos = [], [], 0
    for b in blocks:
        spans.append((pos, pos + len(b.text), b.pages))
        parts.append(b.text)
        pos += len(b.text) + 1
    return "\n".join(parts), spans


def pages_of(start: int, end: int, spans) -> list[int]:
    pages: set[int] = set()
    for s, e, p in spans:
        if s < end and start < e:
            pages |= p
    return sorted(pages)


def split_body(body: str, spans, header: str, max_tokens: int, overlap: int, bullet,
               count: Counter) -> list[tuple[str, list[int]]]:
    """Gövdeyi böler; her parçanın başına başlık yolunu ekler. → [(metin, sayfalar)]"""
    prefix = f"{header}\n" if header else ""
    if count(prefix + body) <= max_tokens:
        return [(prefix + body, pages_of(0, len(body), spans))]
    # Başlık ile gövde birleşince sınırda 1-2 token kayabilir; 2 token pay bırak.
    size = max_tokens - (count(prefix) if prefix else 0) - 2
    if size < MIN_BODY_TOKENS:
        raise ConfigError(f"Başlık yolu çok uzun ({count(prefix)} token), maxTokens'ı büyüt: {header[:80]}…")
    out = []
    for doc in make_splitter(size, min(overlap, size // 2), bullet, count).create_documents([body]):
        start = doc.metadata["start_index"]
        out.append((prefix + doc.page_content, pages_of(start, start + len(doc.page_content), spans)))
    return out


def chunk_heading(sections: list[Section], cfg: dict, bullet, count: Counter) -> list[dict]:
    max_tokens, overlap = cfg["maxTokens"], cfg.get("overlap", 0)
    out = []
    for sec in sections:
        blocks = to_blocks(sec.lines, bullet)
        if not blocks:
            continue  # yalnızca başlık (ör. "7." altında hemen "7.1.1." geliyor)
        body, spans = join_blocks(blocks)
        header = " > ".join(sec.path) if sec.id else ""
        for text, pages in split_body(body, spans, header, max_tokens, overlap, bullet, count):
            out.append({"section": sec.id, "title": sec.title, "path": sec.path if sec.id else [],
                        "text": text, "pages": pages})
    return out


def chunk_fixed(lines: list[Line | None], fixed_cfg: dict, bullet, count: Counter) -> list[dict]:
    body, spans = join_blocks(to_blocks(lines, bullet))
    parts = split_body(body, spans, "", fixed_cfg["maxTokens"], fixed_cfg.get("overlap", 0), bullet, count)
    return [{"section": None, "title": "", "path": [], "text": t, "pages": p} for t, p in parts]


# ---------------------------------------------------------------- ana akış

def main() -> int:
    try:
        project = cli_project("Sayfa metinlerini temizler, bölümlere ayırır ve chunk'lar.")
        cfg = project.get("chunking")
        strategy = project.get("chunking.strategy")
        bullet = cfg.get("bullet")
        pages_file = project.index_dir / "pages.json"
        if not pages_file.exists():
            raise ConfigError(f"{pages_file.relative_to(ROOT)} yok. Önce: python rag/extract.py")
        if strategy == "heading":
            patterns = [re.compile(p) for p in project.get("chunking.headingPatterns")]
        elif strategy != "fixed":
            raise ConfigError(f"Bilinmeyen chunking.strategy: {strategy!r} (heading | fixed)")
        limit = project.get("chunking.maxTokens")
        tokenizer_model = cfg.get("tokenizer") or project.get("embedding.model")
        count = make_token_counter(tokenizer_model)
    except (ConfigError, re.error) as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1

    pages_doc = json.loads(pages_file.read_text(encoding="utf-8"))
    titles = {s["path"]: s.get("title") or s["path"] for s in pages_doc["sources"]}
    print(f"Proje: {project.id} | strateji: {strategy} | token sayımı: {tokenizer_model}")

    chunks: list[dict] = []
    for source, title in titles.items():
        lines = read_lines([p for p in pages_doc["pages"] if p["source"] == source])
        used = strategy
        if strategy == "heading":
            sections = detect_sections(lines, patterns, title)
            found = [s for s in sections if s.id]
            if found:
                part = chunk_heading(sections, cfg, bullet, count)
                untitled = [s.id for s in found if not s.title]
                print(f"\n{source}: {len(found)} bölüm bulundu"
                      + (f" (başlıksız: {', '.join(untitled)})" if untitled else ""))
            else:
                fb = cfg.get("fallback")
                if not fb:
                    print(f"Ayar hatası: {source} içinde başlık bulunamadı ve chunking.fallback yok.", file=sys.stderr)
                    return 1
                used = "fixed (fallback)"
                part = chunk_fixed(lines, fb, bullet, count)
                print(f"\n{source}: başlık bulunamadı → fixed fallback")
        else:
            part = chunk_fixed(lines, cfg, bullet, count)
        for c in part:
            c["source"], c["strategy"] = source, used
        chunks.extend(part)

    # id'ler: <proje>-<bölüm>-<sıra>
    out_chunks, seen = [], {}
    for c in chunks:
        key = c["section"] or "0"
        n = seen.get(key, 0)
        seen[key] = n + 1
        out_chunks.append({
            "id": f"{project.id}-{key}-{n}",
            "text": c["text"],
            "tokens": count(c["text"]),
            "metadata": {"source": c["source"], "section": c["section"], "title": c["title"],
                         "path": c["path"], "pages": c["pages"]},
        })

    output = {
        "schemaVersion": SCHEMA_VERSION,
        "project": project.id,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "chunking": {**cfg, "tokenizer": tokenizer_model},
        "chunks": out_chunks,
    }
    out_file = project.index_dir / "chunks.json"
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    toks = [c["tokens"] for c in out_chunks]
    chars = [len(c["text"]) for c in out_chunks]
    over = [c["id"] for c in out_chunks if c["tokens"] > limit]
    print(f"\nChunk sayısı: {len(toks)}")
    print(f"Token:    min {min(toks)}, medyan {int(statistics.median(toks))}, max {max(toks)} (sınır {limit})")
    print(f"Karakter: min {min(chars)}, medyan {int(statistics.median(chars))}, max {max(chars)}")
    print(f"Sınırı aşan: {over or 'yok'}")
    print(f"→ {out_file.relative_to(ROOT)}")
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
