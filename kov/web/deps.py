from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kov.config import AppConfig


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


def get_qdrant(request: Request):
    return request.app.state.qdrant


def get_s3(request: Request):
    return request.app.state.s3


def get_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.db_sessionmaker


async def get_db_session(
    sessionmaker: Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)],
) -> AsyncSession:
    async with sessionmaker() as session:
        yield session

