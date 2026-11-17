"""E5 ailesi (ör. intfloat/multilingual-e5-small) — sentence-transformers ile yerelde.

E5 modelleri önekle eğitildi: belge parçaları "passage: ", sorular "query: " ile başlar.
Önekler yalnızca bu adaptörün içinde kalır; çekirdek sadece kind="document"|"query" iletir.
Vektörler normalize edilir → cosine benzerliği = dot product.

project.json › embedding:
  model      Hugging Face model adı (zorunlu)
  batchSize  (isteğe bağlı) varsayılan 32
"""

from __future__ import annotations

PREFIXES = {"document": "passage: ", "query": "query: "}
DEFAULT_BATCH_SIZE = 32


class E5Provider:
    name = "e5"
    normalized = True

    def __init__(self, cfg: dict):
        from sentence_transformers import SentenceTransformer

        self.model = cfg.get("model")
        if not self.model:
            raise ValueError("embedding.model alanı eksik (e5 sağlayıcısı için zorunlu).")
        self.batch_size = int(cfg.get("batchSize", DEFAULT_BATCH_SIZE))
        self._st = SentenceTransformer(self.model)
        self.dimensions = self._st.get_embedding_dimension()
        self.token_limit = self._st.max_seq_length

    @staticmethod
    def _prefixed(texts: list[str], kind: str) -> list[str]:
        if kind not in PREFIXES:
            raise ValueError(f"Geçersiz kind: {kind!r}. Geçerli: {sorted(PREFIXES)}")
        return [PREFIXES[kind] + t for t in texts]

    def embed(self, texts: list[str], kind: str) -> list[list[float]]:
        vectors = self._st.encode(
            self._prefixed(texts, kind),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > self.batch_size,
        )
        return vectors.tolist()

    def count_tokens(self, texts: list[str], kind: str) -> list[int]:
        tok = self._st.tokenizer
        return [len(tok.encode(t, add_special_tokens=True)) for t in self._prefixed(texts, kind)]
