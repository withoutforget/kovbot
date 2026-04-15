from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels


def create_qdrant_client(url: str) -> QdrantClient:
    return QdrantClient(url=url)


def ensure_collection(client: QdrantClient, name: str, vector_size: int) -> None:
    exists = False
    try:
        client.get_collection(name)
        exists = True
    except Exception:
        exists = False
    if exists:
        return
    client.create_collection(
        collection_name=name,
        vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
    )

