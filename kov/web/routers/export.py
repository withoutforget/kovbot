import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import (
    Dialog,
    Habit,
    HabitLog,
    Message,
    MoodTrackerEntry,
    Scenario,
    UserAnswer,
)
from kov.web.deps import get_db_session

router = APIRouter()


@router.get("/{user_id}")
async def export_user(user_id: str, session: AsyncSession = Depends(get_db_session)) -> dict:
    user_uuid = uuid.UUID(user_id)

    # interview answers
    scenario_res = await session.execute(select(Scenario).where(Scenario.key == "interview"))
    interview = scenario_res.scalar_one_or_none()
    interview_answers: dict[str, str] = {}
    if interview:
        ans_res = await session.execute(
            select(UserAnswer).where(UserAnswer.user_id == user_uuid).where(UserAnswer.scenario_id == interview.id)
        )
        interview_answers = {a.question_key: a.answer_text for a in ans_res.scalars().all()}

    mood_res = await session.execute(
        select(MoodTrackerEntry)
        .where(MoodTrackerEntry.user_id == user_uuid)
        .order_by(MoodTrackerEntry.entry_date.asc())
    )
    moods = [
        {
            "date": str(e.entry_date),
            "mood_score": e.mood_score,
            "notes": e.notes,
            "factors_down": e.factors_down,
            "factors_up": e.factors_up,
        }
        for e in mood_res.scalars().all()
    ]

    habits_res = await session.execute(select(Habit).where(Habit.user_id == user_uuid))
    habits = habits_res.scalars().all()
    logs_res = await session.execute(select(HabitLog).where(HabitLog.user_id == user_uuid))
    logs = logs_res.scalars().all()
    habits_payload = []
    for h in habits:
        hlogs = [l for l in logs if l.habit_id == h.id]
        habits_payload.append(
            {
                "habit_id": str(h.id),
                "title": h.title,
                "description": h.description,
                "archived": h.archived,
                "logs": [{"date": str(l.log_date), "done": l.done, "notes": l.notes} for l in hlogs],
            }
        )

    dialogs_res = await session.execute(select(Dialog).where(Dialog.user_id == user_uuid))
    dialogs = dialogs_res.scalars().all()
    dialog_payload = []
    for d in dialogs:
        msg_res = await session.execute(
            select(Message).where(Message.dialog_id == d.id).order_by(Message.created_at.asc())
        )
        dialog_payload.append(
            {
                "dialog_id": str(d.id),
                "scenario_id": str(d.scenario_id) if d.scenario_id else None,
                "title": d.title,
                "messages": [{"role": m.role, "text": m.text, "created_at": m.created_at.isoformat()} for m in msg_res.scalars().all()],
            }
        )

    return {
        "user_id": user_id,
        "interview": interview_answers,
        "mood_tracker": moods,
        "habits": habits_payload,
        "dialogs": dialog_payload,
    }
