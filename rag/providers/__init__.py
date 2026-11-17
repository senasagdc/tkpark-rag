"""Embedding sağlayıcı adaptörleri.

Her adaptör aynı arayüzü sunar (bkz. EmbeddingProvider):
    embed(texts, kind) -> list[list[float]]     kind: "document" | "query"

Sağlayıcı project.json › embedding.provider ile seçilir.
Yeni sağlayıcı eklemek = yeni modül + PROVIDERS sözlüğüne bir satır.
"""

from __future__ import annotations

from typing import Callable, Literal, Protocol

Kind = Literal["document", "query"]
KINDS: tuple[str, ...] = ("document", "query")


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int
    normalized: bool
    token_limit: int | None   # modelin giriş sınırı (öneki ve özel tokenlar dahil); bilinmiyorsa None

    def embed(self, texts: list[str], kind: Kind) -> list[list[float]]: ...

    def count_tokens(self, texts: list[str], kind: Kind) -> list[int]:
        """Modele gerçekte giden token sayısı (önek + özel tokenlar dahil)."""
        ...


def _e5(cfg: dict) -> EmbeddingProvider:
    from . import e5  # sentence-transformers yalnızca bu sağlayıcı seçiliyse yüklensin
    return e5.E5Provider(cfg)


PROVIDERS: dict[str, Callable[[dict], EmbeddingProvider]] = {
    "e5": _e5,
}


def get_provider(cfg: dict) -> EmbeddingProvider:
    """cfg = project.json › embedding ({"provider": ..., "model": ..., ...})."""
    name = cfg.get("provider")
    try:
        factory = PROVIDERS[name]
    except KeyError:
        raise ValueError(
            f"Desteklenmeyen embedding sağlayıcısı: {name!r}. Desteklenenler: {sorted(PROVIDERS)}"
        ) from None
    return factory(cfg)
