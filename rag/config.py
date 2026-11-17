"""Aktif projenin ayarlarını yükler.

Proje seçimi (öncelik sırasıyla):
  1. --project <id> argümanı
  2. PROJECT ortam değişkeni
  3. .env dosyasındaki PROJECT

Projeye özel hiçbir değer bu dosyada yoktur; hepsi projects/<id>/project.json'dan gelir.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT / "projects"
INDEX_DIR = ROOT / "index"
ENV_FILE = ROOT / ".env"

_MISSING = object()


class ConfigError(Exception):
    """Ayar dosyası eksik veya hatalı."""


def load_env(path: Path = ENV_FILE) -> None:
    """.env dosyasını okur. Zaten tanımlı ortam değişkenlerinin üzerine yazmaz."""
    if not path.exists():
        return
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"{path.name}:{line_no}: 'ANAHTAR=değer' biçiminde değil: {raw!r}")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Project:
    id: str
    dir: Path
    index_dir: Path
    data: dict

    def get(self, dotted: str, default=_MISSING):
        """'embedding.model' gibi noktalı yolla değer okur.

        Değer yoksa ve default verilmemişse açık bir hata verir.
        """
        node = self.data
        for part in dotted.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                if default is _MISSING:
                    raise ConfigError(
                        f"{self.dir.relative_to(ROOT)}/project.json: '{dotted}' alanı eksik."
                    )
                return default
        return node

    def path(self, relative: str) -> Path:
        """Proje klasörüne göre göreli yolu mutlak yola çevirir."""
        return self.dir / relative


def _validate(project: Project) -> None:
    where = f"{project.dir.relative_to(ROOT)}/project.json"

    file_id = project.get("id")
    if file_id != project.id:
        raise ConfigError(
            f"{where}: 'id' ({file_id!r}) klasör adıyla ({project.id!r}) aynı olmalı."
        )

    sources = project.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ConfigError(f"{where}: 'sources' boş olmayan bir liste olmalı.")

    for i, src in enumerate(sources):
        for field in ("path", "type"):
            if not src.get(field):
                raise ConfigError(f"{where}: sources[{i}].{field} alanı eksik.")
        if not project.path(src["path"]).exists():
            raise ConfigError(f"{where}: sources[{i}].path bulunamadı: {src['path']}")


def load_project(project_id: str | None = None) -> Project:
    load_env()
    project_id = project_id or os.environ.get("PROJECT")
    if not project_id:
        raise ConfigError(
            "Aktif proje seçilmedi. .env içine PROJECT=<id> yaz veya --project <id> kullan."
        )

    project_dir = PROJECTS_DIR / project_id
    config_file = project_dir / "project.json"
    if not config_file.exists():
        available = sorted(
            p.name for p in PROJECTS_DIR.iterdir()
            if (p / "project.json").exists() and not p.name.startswith("_")
        ) if PROJECTS_DIR.exists() else []
        raise ConfigError(
            f"Proje bulunamadı: {config_file.relative_to(ROOT)}. Mevcut projeler: {available}"
        )

    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"{config_file.relative_to(ROOT)}: geçersiz JSON ({e})") from e

    project = Project(
        id=project_id,
        dir=project_dir,
        index_dir=INDEX_DIR / project_id,
        data=data,
    )
    _validate(project)
    return project


def cli_project(description: str) -> Project:
    """Script'ler için ortak giriş: --project argümanını okur ve projeyi yükler."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--project", help="projects/ altındaki proje klasörü (varsayılan: .env PROJECT)")
    args = parser.parse_args()
    return load_project(args.project)
