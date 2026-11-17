"""Kaynak türüne göre belge okuyucular.

Her loader aynı imzaya sahiptir:
    load(path: Path, source: dict) -> LoadedSource

Yeni tür eklemek = yeni modül + LOADERS sözlüğüne bir satır.
"""

from __future__ import annotations

from typing import Callable, TypedDict


class Page(TypedDict):
    page: int    # kaynak içindeki sıra numarası (PDF'te PDF sayfası, 1'den başlar)
    text: str


class LoadedSource(TypedDict):
    numPages: int
    skippedPages: list[int]
    pages: list[Page]
    metadata: dict


def _pdf(path, source):
    from . import pdf  # PyMuPDF yalnızca PDF kaynağı varsa gereksin
    return pdf.load(path, source)


LOADERS: dict[str, Callable[..., LoadedSource]] = {
    "pdf": _pdf,
}


def get_loader(source_type: str) -> Callable[..., LoadedSource]:
    try:
        return LOADERS[source_type]
    except KeyError:
        raise ValueError(
            f"Desteklenmeyen kaynak türü: {source_type!r}. Desteklenenler: {sorted(LOADERS)}"
        ) from None
