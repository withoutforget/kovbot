from __future__ import annotations

from contextlib import asynccontextmanager

from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from kov.config import load_config
from kov.di.providers import AppProvider
from kov.db.base import Base
from kov.logging import configure_logging, get_logger
from kov.web.routers.health import router as health_router
from kov.web.routers.habits import router as habits_router
from kov.web.routers.dialog import router as dialog_router
from kov.web.routers.export import router as export_router
from kov.web.routers.llm import router as llm_router
from kov.web.routers.mood import router as mood_router
from kov.web.routers.rag_scan import router as rag_scan_router
from kov.web.routers.rag_search import router as rag_search_router
from kov.web.routers.ragd import router as rag_debug_router
from kov.web.routers.reports import router as reports_router
from kov.web.routers.scenarios import router as scenarios_router
from kov.web.routers.schedule import router as schedule_router
from kov.web.routers.techniques import router as techniques_router
from kov.web.routers.users import router as users_router
from kov.web.seed import seed_scenarios


def create_app() -> FastAPI:
    config = load_config()
    configure_logging(config.logging.level)
    log = get_logger(component="api")
    log.info("starting_api", env=config.env)

    provider = AppProvider(config)
    container = make_async_container(provider)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from sqlalchemy.ext.asyncio import AsyncEngine

        engine = await container.get(AsyncEngine)
        # Backward-compatible app.state for routers that use fastapi Depends(get_db_session) etc.
        # Newer routers use Dishka injection directly.
        app.state.config = config
        app.state.db_engine = engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # seed scenarios
        from sqlalchemy.ext.asyncio import async_sessionmaker

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        app.state.db_sessionmaker = sessionmaker

        from qdrant_client import QdrantClient

        app.state.qdrant = await container.get(QdrantClient)
        from botocore.client import BaseClient

        app.state.s3 = await container.get(BaseClient)

        async with sessionmaker() as session:
            await seed_scenarios(session)
        yield
        await container.close()
        await engine.dispose()

    app = FastAPI(title="Kov API", version="0.1.0", lifespan=lifespan)
    setup_dishka(container, app)

    app.include_router(health_router, tags=["health"])
    app.include_router(users_router, prefix="/users", tags=["users"])
    app.include_router(scenarios_router, prefix="/scenarios", tags=["scenarios"])
    app.include_router(mood_router, prefix="/mood", tags=["mood"])
    app.include_router(habits_router, prefix="/habits", tags=["habits"])
    app.include_router(reports_router, prefix="/reports", tags=["reports"])
    app.include_router(schedule_router, prefix="/schedule", tags=["schedule"])
    app.include_router(dialog_router, prefix="/dialog", tags=["dialog"])
    app.include_router(techniques_router, prefix="/techniques", tags=["techniques"])
    app.include_router(export_router, prefix="/export", tags=["export"])
    app.include_router(llm_router, prefix="/llm", tags=["llm"])
    app.include_router(rag_scan_router, prefix="/rag/scan", tags=["rag_scan"])
    app.include_router(rag_search_router, prefix="/rag/search", tags=["rag_search"])
    app.include_router(rag_debug_router, prefix="/ragd", tags=["rag_debug"])
    return app


app = create_app()
