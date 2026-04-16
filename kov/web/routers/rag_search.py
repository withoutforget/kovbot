import uuid

from botocore.client import BaseClient
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from kov.config import AppConfig
from kov.rag.search.service import RagSearchService
from kov.rag.types import RagAnswer
router = APIRouter(route_class=DishkaRoute)


class RagSearchRequest(BaseModel):
    user_query: str
    user_id: str | None = None
    scenario_id: str = ""
    language: str = "ru"
    search_profile: str = "quick_advice"


@router.post("", response_model=RagAnswer)
async def rag_search(
    req: RagSearchRequest,
    config: FromDishka[AppConfig],
    session: FromDishka[AsyncSession],
    qdrant: FromDishka[QdrantClient],
    s3: FromDishka[BaseClient],
) -> RagAnswer:
    service = RagSearchService(config=config, session=session, qdrant=qdrant, s3=s3)
    user_uuid = uuid.UUID(req.user_id) if req.user_id else None
    return await service.search(
        user_query=req.user_query,
        user_id=user_uuid,
        scenario_id=req.scenario_id,
        language=req.language,
        search_profile=req.search_profile,
    )


@router.post("/stream")
async def rag_search_stream(
    req: RagSearchRequest,
    config: FromDishka[AppConfig],
    session: FromDishka[AsyncSession],
    qdrant: FromDishka[QdrantClient],
    s3: FromDishka[BaseClient],
):
    service = RagSearchService(config=config, session=session, qdrant=qdrant, s3=s3)
    user_uuid = uuid.UUID(req.user_id) if req.user_id else None

    async def gen():
        # run retrieval/expansion same as /rag/search, but stream the final LLM output
        plan = await service.search_debug(
            user_query=req.user_query,
            user_id=user_uuid,
            scenario_id=req.scenario_id,
            language=req.language,
            search_profile=req.search_profile,
        )
        expanded = plan.get("expanded_contexts") or []
        profile_summary = await service._get_profile_summary(user_id=user_uuid)
        async for delta in service.compose_answer_llm_stream(
            user_query=req.user_query,
            language=req.language,
            expanded_contexts=expanded,
            user_profile_summary=profile_summary,
        ):
            yield delta.encode("utf-8")

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")
