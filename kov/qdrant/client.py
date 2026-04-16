from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels


def create_qdrant_client(url: str, *, timeout_seconds: int = 120) -> QdrantClient:
    # QdrantClient uses httpx under the hood; for large upserts defaults can be too tight.
    return QdrantClient(url=url, timeout=timeout_seconds, prefer_grpc=False)


def ensure_collection(client: QdrantClient, name: str, vector_size: int) -> None:
    exists = False
    try:
        info = client.get_collection(name)
        exists = True
    except Exception:
        exists = False
    if exists:
        try:
            vectors = info.config.params.vectors  # type: ignore[attr-defined]
            existing_size = None
            if hasattr(vectors, "size"):
                existing_size = int(vectors.size)  # type: ignore[attr-defined]
            elif isinstance(vectors, dict) and vectors:
                first = next(iter(vectors.values()))
                if hasattr(first, "size"):
                    existing_size = int(first.size)  # type: ignore[attr-defined]
            if existing_size is not None and existing_size != int(vector_size):
                raise RuntimeError(
                    f"Qdrant collection '{name}' exists with vector size {existing_size}, "
                    f"but config requires {vector_size}. Delete the collection/volume or change collection name."
                )
        except Exception as e:
            # If we can't reliably validate, don't block startup.
            if isinstance(e, RuntimeError):
                raise
        return
    client.create_collection(
        collection_name=name,
        vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
    )
