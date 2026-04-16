from __future__ import annotations

import pytest

from kov.embeddings.openai_compat import OpenAICompatEmbeddingsConfig, OpenAICompatEmbedder


@pytest.mark.asyncio
async def test_openai_compat_embedder_batches(httpx_mock):
    httpx_mock.add_response(
        url="https://example.test/v1/embeddings",
        json={"data": [{"embedding": [0.0, 0.0]}, {"embedding": [1.0, 1.0]}]},
    )
    httpx_mock.add_response(
        url="https://example.test/v1/embeddings",
        json={"data": [{"embedding": [2.0, 2.0]}]},
    )

    embedder = OpenAICompatEmbedder(
        OpenAICompatEmbeddingsConfig(
            base_url="https://example.test",
            api_key="x",
            model="m",
            vector_size=2,
            batch_size=2,
        )
    )
    vectors = await embedder.embed(["a", "b", "c"])
    assert vectors == [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]]

