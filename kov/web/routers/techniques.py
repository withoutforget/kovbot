from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import Scenario, UserAnswer
from kov.web.deps import get_db_session

router = APIRouter()


class TechniqueSuggestion(BaseModel):
    kind: str  # express/deep
    title: str
    steps: list[str]


class TechniqueRequest(BaseModel):
    user_id: str
    query: str


class TechniqueResponse(BaseModel):
    suggestions: list[TechniqueSuggestion]

TECHNIQUE_LIBRARY: list[TechniqueSuggestion] = [
    TechniqueSuggestion(
        kind="express",
        title="Заземление 5-4-3-2-1",
        steps=[
            "Назовите 5 предметов вокруг",
            "Назовите 4 ощущения тела",
            "Назовите 3 звука",
            "Назовите 2 запаха",
            "Назовите 1 вкус или мысль-опору",
        ],
    ),
    TechniqueSuggestion(
        kind="express",
        title="Дыхание 4-6",
        steps=["Вдох 4 секунды", "Выдох 6 секунд", "Повторите 8–12 циклов"],
    ),
    TechniqueSuggestion(
        kind="deep",
        title="Таблица мыслей (КПТ)",
        steps=[
            "Опишите ситуацию (что произошло?)",
            "Запишите автоматическую мысль",
            "Оцените эмоции (0–100)",
            "Найдите доказательства 'за' и 'против'",
            "Сформулируйте более сбалансированную мысль",
            "Переоцените эмоции (0–100)",
        ],
    ),
    TechniqueSuggestion(
        kind="deep",
        title="План поведенческого шага",
        steps=[
            "Выберите один маленький шаг на 10–15 минут",
            "Опишите, когда и где вы сделаете его",
            "Определите препятствие и план 'если-то'",
            "Отметьте выполнение и эффект",
        ],
    ),
]


@router.post("", response_model=TechniqueResponse)
async def suggest_techniques(req: TechniqueRequest, session: AsyncSession = Depends(get_db_session)) -> TechniqueResponse:
    user_uuid = uuid.UUID(req.user_id)
    res = await session.execute(select(Scenario).where(Scenario.key == "techniques"))
    scenario = res.scalar_one_or_none()
    scenario_id = scenario.id if scenario else None
    if not scenario_id:
        # fallback if seed not ready
        return TechniqueResponse(suggestions=TECHNIQUE_LIBRARY[:2])

    # store request
    session.add(
        UserAnswer(
            id=uuid.uuid4(),
            user_id=user_uuid,
            scenario_id=scenario_id,
            question_key="technique_request",
            answer_text=req.query,
        )
    )

    # reduce repetition: avoid titles already suggested recently
    prev_res = await session.execute(
        select(UserAnswer)
        .where(and_(UserAnswer.user_id == user_uuid, UserAnswer.scenario_id == scenario_id))
        .where(UserAnswer.question_key == "technique_suggestion")
        .order_by(UserAnswer.created_at.desc())
        .limit(20)
    )
    seen = {a.answer_text for a in prev_res.scalars().all()}
    candidates = [t for t in TECHNIQUE_LIBRARY if t.title not in seen] or TECHNIQUE_LIBRARY
    # pick one express and one deep if possible
    express = next((t for t in candidates if t.kind == "express"), candidates[0])
    deep = next((t for t in candidates if t.kind == "deep" and t.title != express.title), candidates[-1])

    session.add(
        UserAnswer(
            id=uuid.uuid4(),
            user_id=user_uuid,
            scenario_id=scenario_id,
            question_key="technique_suggestion",
            answer_text=express.title,
        )
    )
    session.add(
        UserAnswer(
            id=uuid.uuid4(),
            user_id=user_uuid,
            scenario_id=scenario_id,
            question_key="technique_suggestion",
            answer_text=deep.title,
        )
    )
    await session.commit()
    return TechniqueResponse(suggestions=[express, deep])


class TechniqueDoneRequest(BaseModel):
    user_id: str
    title: str


@router.post("/done")
async def mark_done(req: TechniqueDoneRequest, session: AsyncSession = Depends(get_db_session)) -> dict[str, bool]:
    user_uuid = uuid.UUID(req.user_id)
    res = await session.execute(select(Scenario).where(Scenario.key == "techniques"))
    scenario = res.scalar_one_or_none()
    if scenario:
        session.add(
            UserAnswer(
                id=uuid.uuid4(),
                user_id=user_uuid,
                scenario_id=scenario.id,
                question_key="technique_done",
                answer_text=req.title,
            )
        )
        await session.commit()
    return {"ok": True}
