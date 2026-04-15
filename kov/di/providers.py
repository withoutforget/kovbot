from __future__ import annotations

from collections.abc import AsyncIterator

from botocore.client import BaseClient
from dishka import Provider, Scope, provide
from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from kov.config import AppConfig
from kov.qdrant.client import create_qdrant_client, ensure_collection
from kov.s3.client import create_s3_client, ensure_bucket


class AppProvider(Provider):
    def __init__(self, config: AppConfig):
        super().__init__()
        self._config = config

    @provide(scope=Scope.APP)
    def config(self) -> AppConfig:
        return self._config

    @provide(scope=Scope.APP)
    def engine(self, config: AppConfig) -> AsyncEngine:
        return create_async_engine(config.postgres.dsn, pool_pre_ping=True)

    @provide(scope=Scope.APP)
    def sessionmaker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(engine, expire_on_commit=False)

    @provide(scope=Scope.REQUEST)
    async def session(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    @provide(scope=Scope.APP)
    def qdrant(self, config: AppConfig) -> QdrantClient:
        client = create_qdrant_client(config.qdrant.url)
        ensure_collection(client, config.qdrant.collection, config.qdrant.vector_size)
        return client

    @provide(scope=Scope.APP)
    def s3(self, config: AppConfig) -> BaseClient:
        s3 = create_s3_client(
            endpoint_url=config.s3.endpoint_url,
            access_key=config.s3.access_key,
            secret_key=config.s3.secret_key,
            region=config.s3.region,
        )
        ensure_bucket(s3, config.s3.bucket)
        return s3

