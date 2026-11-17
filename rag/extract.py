"""Aktif projenin kaynaklarını okur → index/<proje-id>/pages.json

Kullanım:
    python rag/extract.py                 # .env › PROJECT
    python rag/extract.py --project <id>
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from config import ROOT, ConfigError, cli_project
from loaders import get_loader

SCHEMA_VERSION = 1
LOW_TEXT_CHARS = 50  # yalnızca uyarı: bu kadar az metinli sayfa taranmış olabilir


def main() -> int:
    try:
        project = cli_project("Kaynak belgelerden sayfa metinlerini çıkarır.")
    except ConfigError as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 1

    print(f"Proje: {project.id}")
    sources_out, pages_out = [], []

    for src in project.get("sources"):
        path = project.path(src["path"])
        print(f"\nOkunuyor: {src['path']} ({src['type']})")
        loaded = get_loader(src["type"])(path, src)

        low_text = [p["page"] for p in loaded["pages"] if len(p["text"]) < LOW_TEXT_CHARS]
        print(f"  Sayfa sayısı: {loaded['numPages']}")
        print(f"  Atlanan sayfalar: {loaded['skippedPages']}")
        print(f"  Alınan sayfalar: {len(loaded['pages'])}")
        print(f"  Az metinli sayfalar: {low_text}")
        print(f"  Oluşturulma tarihi: {loaded['metadata'].get('creationDate')}")

        sources_out.append({
            "path": src["path"],
            "type": src["type"],
            "title": src.get("title"),
            "numPages": loaded["numPages"],
            "skippedPages": loaded["skippedPages"],
            "metadata": loaded["metadata"],
        })
        pages_out.extend({"source": src["path"], **p} for p in loaded["pages"])

    output = {
        "schemaVersion": SCHEMA_VERSION,
        "project": project.id,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": sources_out,
        "pages": pages_out,
    }

    project.index_dir.mkdir(parents=True, exist_ok=True)
    out_file = project.index_dir / "pages.json"
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    chars = sum(len(p["text"]) for p in pages_out)
    print(f"\nToplam: {len(pages_out)} sayfa, {chars:,} karakter → {out_file.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
