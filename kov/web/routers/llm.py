from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from kov.config import AppConfig
from kov.llm.openai_compat import OpenAICompatClient
router = APIRouter(route_class=DishkaRoute)


class LlmProxyRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list)
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class LlmProxyResponse(BaseModel):
    text: str
    raw: dict[str, Any]


async def _proxy(config: AppConfig, req: LlmProxyRequest) -> LlmProxyResponse:
    client = OpenAICompatClient(config.llm)
    try:
        raw = await client.chat_completions(
            messages=req.messages,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return LlmProxyResponse(text=client.extract_text(raw), raw=raw)


@router.post("/chat", response_model=LlmProxyResponse)
async def llm_chat(req: LlmProxyRequest, config: FromDishka[AppConfig]) -> LlmProxyResponse:
    return await _proxy(config, req)


@router.post("/query-planner", response_model=LlmProxyResponse)
async def llm_query_planner(
    req: LlmProxyRequest, config: FromDishka[AppConfig]
) -> LlmProxyResponse:
    return await _proxy(config, req)


@router.post("/reranker", response_model=LlmProxyResponse)
async def llm_reranker(
    req: LlmProxyRequest, config: FromDishka[AppConfig]
) -> LlmProxyResponse:
    return await _proxy(config, req)


@router.post("/answer-generator", response_model=LlmProxyResponse)
async def llm_answer_generator(
    req: LlmProxyRequest, config: FromDishka[AppConfig]
) -> LlmProxyResponse:
    return await _proxy(config, req)


@router.post("/extract-entities", response_model=LlmProxyResponse)
async def llm_extract_entities(
    req: LlmProxyRequest, config: FromDishka[AppConfig]
) -> LlmProxyResponse:
    return await _proxy(config, req)
