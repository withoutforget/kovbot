from __future__ import annotations

import hashlib

from kov.embeddings.base import Embedder


class FakeEmbedder(Embedder):
    def __init__(self, vector_size: int):
        self.vector_size = vector_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            raw = list(digest) * ((self.vector_size // len(digest)) + 1)
            v = [(b / 255.0) for b in raw[: self.vector_size]]
            vectors.append(v)
        return vectors

