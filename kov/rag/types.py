from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NormalizedState(BaseModel):
    summary: str = ""
    symptoms: list[str] = Field(default_factory=list)
    situations: list[str] = Field(default_factory=list)
    goal: str = ""
    urgency: str = "normal"
    crisis_signals: list[str] = Field(default_factory=list)


class SearchQueryPlanItem(BaseModel):
    query_id: str
    text: str
    intent_type: str = "mixed"
    weight: float = 1.0
    topic_tags: list[str] = Field(default_factory=list)
    approach_tags: list[str] = Field(default_factory=list)
    preferred_content_types: list[str] = Field(default_factory=list)
    expected_granularity: str = "chunk"


class SearchPlan(BaseModel):
    schema_version: str = "1.0"
    request_id: str
    user_query: str
    language: str = "ru"
    search_profile: str = "quick_advice"
    normalized_state: NormalizedState = Field(default_factory=NormalizedState)
    global_filters: dict[str, Any] = Field(default_factory=dict)
    queries: list[SearchQueryPlanItem] = Field(default_factory=list)


class TelegramMessagePart(BaseModel):
    part: int
    total_parts: int
    text: str


class RagAnswer(BaseModel):
    request_id: str
    answer_type: str = "quick_advice"
    summary: str = ""
    advice_items: list[dict[str, Any]] = Field(default_factory=list)
    telegram_messages: list[TelegramMessagePart] = Field(default_factory=list)

