from __future__ import annotations

from dataclasses import dataclass

import httpx

from kov.embeddings.base import Embedder


@dataclass(frozen=True)
class OpenAICompatEmbeddingsConfig:
    base_url: str
    api_key: str
    model: str
    vector_size: int
    batch_size: int = 64


class OpenAICompatEmbedder(Embedder):
    def __init__(self, config: OpenAICompatEmbeddingsConfig):
        self._config = config

    def _embeddings_url(self) -> str:
        base = (self._config.base_url or "").rstrip("/")
        if not base:
            raise RuntimeError("Embeddings base_url is empty")
        if base.endswith("/embeddings"):
            return base
        if base.endswith("/v1"):
            return base + "/embeddings"
        if base.endswith("/v1/embeddings"):
            return base
        return base + "/v1/embeddings"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._config.api_key or not self._config.model:
            raise RuntimeError("Embeddings is not configured (api_key/model)")
        if not texts:
            return []

        headers = {"Authorization": f"Bearer {self._config.api_key}"}

        url = self._embeddings_url()
        batch_size = max(1, int(self._config.batch_size or 64))

        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for start in range(0, len(texts), batch_size):
                chunk = texts[start : start + batch_size]
                payload = {"model": self._config.model, "input": chunk}
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code >= 400:
                    detail = resp.text
                    raise RuntimeError(
                        f"Embeddings HTTP {resp.status_code} from {url}: {detail[:500]}"
                    )
                data = resp.json()

                items = data.get("data") or []
                if len(items) != len(chunk):
                    raise RuntimeError(
                        f"Embeddings response mismatch: got {len(items)} for {len(chunk)} inputs"
                    )

                for item in items:
                    emb = item.get("embedding")
                    if not isinstance(emb, list):
                        raise RuntimeError("Embeddings response item has no embedding[]")
                    vec = [float(x) for x in emb]
                    if self._config.vector_size and len(vec) != self._config.vector_size:
                        raise RuntimeError(
                            f"Embedding dim mismatch: got {len(vec)}, expected {self._config.vector_size}. "
                            f"Fix qdrant.vector_size or use another model."
                        )
                    vectors.append(vec)
        return vectors
