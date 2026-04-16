from __future__ import annotations

from kov.config import AppConfig
from kov.embeddings.base import Embedder
from kov.embeddings.fake import FakeEmbedder
from kov.embeddings.openai_compat import OpenAICompatEmbeddingsConfig, OpenAICompatEmbedder


def create_embedder(config: AppConfig) -> Embedder:
    provider = (config.embeddings.provider or "fake").lower()
    if provider in {"openai", "openai_compat", "proxyapi"}:
        return OpenAICompatEmbedder(
            OpenAICompatEmbeddingsConfig(
                base_url=config.embeddings.base_url,
                api_key=config.embeddings.api_key,
                model=config.embeddings.model,
                vector_size=config.qdrant.vector_size,
                batch_size=config.embeddings.batch_size,
            )
        )
    return FakeEmbedder(vector_size=config.qdrant.vector_size)
