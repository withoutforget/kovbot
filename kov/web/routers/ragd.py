import uuid

from botocore.client import BaseClient
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from kov.config import AppConfig
from kov.rag.search.service import RagSearchService

router = APIRouter(route_class=DishkaRoute)


class RagDebugRequest(BaseModel):
    user_query: str
    user_id: str | None = None
    scenario_id: str = ""
    language: str = "ru"
    search_profile: str = "quick_advice"


@router.post("", response_model=dict)
async def rag_debug(
    req: RagDebugRequest,
    config: FromDishka[AppConfig],
    session: FromDishka[AsyncSession],
    qdrant: FromDishka[QdrantClient],
    s3: FromDishka[BaseClient],
) -> dict:
    service = RagSearchService(config=config, session=session, qdrant=qdrant, s3=s3)
    user_uuid = uuid.UUID(req.user_id) if req.user_id else None
    return await service.search_debug(
        user_query=req.user_query,
        user_id=user_uuid,
        scenario_id=req.scenario_id,
        language=req.language,
        search_profile=req.search_profile,
    )

