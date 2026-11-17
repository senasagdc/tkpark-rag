"""PDF okuyucu (PyMuPDF).

Kaynak ayarları (project.json › sources[i]):
  skipPages: indekse alınmayacak PDF sayfaları, 1'den başlar (ör. kapak, içindekiler)
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from . import LoadedSource


def _pdf_date(value: str | None) -> str | None:
    """PDF tarih biçimini ('D:20250128093000+03'00'') ISO tarihe çevirir."""
    if not value:
        return None
    m = re.match(r"D:(\d{4})(\d{2})?(\d{2})?", value)
    if not m:
        return None
    year, month, day = m.group(1), m.group(2) or "01", m.group(3) or "01"
    return f"{year}-{month}-{day}"


def load(path: Path, source: dict) -> LoadedSource:
    skip = set(source.get("skipPages", []))

    with pymupdf.open(path) as doc:
        num_pages = doc.page_count
        invalid = sorted(p for p in skip if not 1 <= p <= num_pages)
        if invalid:
            raise ValueError(f"{path.name}: skipPages aralık dışında {invalid} (sayfa sayısı {num_pages})")

        pages = []
        for index, page in enumerate(doc):
            number = index + 1  # PDF sayfa sırası; basılı sayfa numarası değil
            if number in skip:
                continue
            pages.append({"page": number, "text": page.get_text("text").strip()})

        meta = doc.metadata or {}

    return {
        "numPages": num_pages,
        "skippedPages": sorted(skip),
        "pages": pages,
        "metadata": {
            "title": meta.get("title") or None,
            "author": meta.get("author") or None,
            "creationDate": _pdf_date(meta.get("creationDate")),
            "modDate": _pdf_date(meta.get("modDate")),
        },
    }
