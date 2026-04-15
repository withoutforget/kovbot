from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from kov.config import AppConfig
from kov.db.base import Base
from kov.db.session import create_engine_and_sessionmaker
from kov.logging import get_logger
from kov.qdrant.client import create_qdrant_client, ensure_collection
from kov.s3.client import create_s3_client, ensure_bucket
from kov.web.seed import seed_scenarios


@asynccontextmanager
async def lifespan(app: FastAPI, config: AppConfig):
    log = get_logger(component="lifespan")
    engine, sessionmaker = create_engine_and_sessionmaker(config.postgres.dsn)
    app.state.db_engine = engine
    app.state.db_sessionmaker = sessionmaker

    qdrant = create_qdrant_client(config.qdrant.url)
    ensure_collection(qdrant, config.qdrant.collection, config.qdrant.vector_size)
    app.state.qdrant = qdrant

    s3 = create_s3_client(
        endpoint_url=config.s3.endpoint_url,
        access_key=config.s3.access_key,
        secret_key=config.s3.secret_key,
        region=config.s3.region,
    )
    ensure_bucket(s3, config.s3.bucket)
    app.state.s3 = s3
    app.state.config = config

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with sessionmaker() as session:
        await seed_scenarios(session)

    log.info("app_ready")
    try:
        yield
    finally:
        log.info("app_stopping")
        await engine.dispose()


def register_lifespan(app: FastAPI, config: AppConfig) -> None:
    app.router.lifespan_context = lambda _: lifespan(app, config)
