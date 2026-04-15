from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import Scenario, UserAnswer, UserProfile
from kov.web.deps import get_db_session

router = APIRouter()


class ScenarioInfo(BaseModel):
    id: str
    key: str
    title: str
    description: str
    enabled: bool


@router.get("", response_model=list[ScenarioInfo])
async def list_scenarios(session: AsyncSession = Depends(get_db_session)) -> list[ScenarioInfo]:
    res = await session.execute(select(Scenario).order_by(Scenario.key.asc()))
    items = []
    for s in res.scalars().all():
        items.append(
            ScenarioInfo(id=str(s.id), key=s.key, title=s.title, description=s.description, enabled=s.enabled)
        )
    return items


INTERVIEW_QUESTIONS: list[tuple[str, str]] = [
    ("name", "Как я могу к вам обращаться?"),
    ("state", "Как вы себя сейчас чувствуете?"),
    ("goals", "Что бы вы хотели изменить или получить от поддержки?"),
    ("difficulties", "Что даётся особенно тяжело в последнее время?"),
    ("support", "Что обычно помогает вам хоть немного?"),
]


class InterviewQuestion(BaseModel):
    question_key: str
    text: str


class InterviewStartResponse(BaseModel):
    questions: list[InterviewQuestion]


@router.post("/interview/start", response_model=InterviewStartResponse)
async def interview_start() -> InterviewStartResponse:
    return InterviewStartResponse(
        questions=[InterviewQuestion(question_key=k, text=t) for k, t in INTERVIEW_QUESTIONS]
    )


class InterviewAnswerRequest(BaseModel):
    user_id: str
    question_key: str
    answer_text: str


class InterviewAnswerResponse(BaseModel):
    ok: bool


@router.post("/interview/answer", response_model=InterviewAnswerResponse)
async def interview_answer(
    req: InterviewAnswerRequest, session: AsyncSession = Depends(get_db_session)
) -> InterviewAnswerResponse:
    user_uuid = uuid.UUID(req.user_id)
    res = await session.execute(select(Scenario).where(Scenario.key == "interview"))
    scenario = res.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=500, detail="Scenario interview not seeded")
    existing_res = await session.execute(
        select(UserAnswer)
        .where(and_(UserAnswer.user_id == user_uuid, UserAnswer.scenario_id == scenario.id))
        .where(UserAnswer.question_key == req.question_key)
        .order_by(UserAnswer.created_at.desc())
        .limit(1)
    )
    existing = existing_res.scalar_one_or_none()
    if existing:
        existing.answer_text = req.answer_text
    else:
        session.add(
            UserAnswer(
                id=uuid.uuid4(),
                user_id=user_uuid,
                scenario_id=scenario.id,
                question_key=req.question_key,
                answer_text=req.answer_text,
            )
        )
    await session.commit()
    return InterviewAnswerResponse(ok=True)


class InterviewViewResponse(BaseModel):
    answers: dict[str, str]
    summary: str


@router.get("/interview/{user_id}", response_model=InterviewViewResponse)
async def interview_view(user_id: str, session: AsyncSession = Depends(get_db_session)) -> InterviewViewResponse:
    user_uuid = uuid.UUID(user_id)
    res = await session.execute(select(Scenario).where(Scenario.key == "interview"))
    scenario = res.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=500, detail="Scenario interview not seeded")
    res = await session.execute(
        select(UserAnswer).where(and_(UserAnswer.user_id == user_uuid, UserAnswer.scenario_id == scenario.id))
    )
    answers = {a.question_key: a.answer_text for a in res.scalars().all()}
    summary = "; ".join([f"{k}={v}" for k, v in answers.items()])[:1000]

    # store summary in profile for personalization
    prof_res = await session.execute(select(UserProfile).where(UserProfile.user_id == user_uuid))
    profile = prof_res.scalar_one_or_none()
    if profile:
        profile.interview_summary = summary
        await session.commit()
    return InterviewViewResponse(answers=answers, summary=summary)
