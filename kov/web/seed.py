from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kov.db.models import Scenario


DEFAULT_SCENARIOS: list[dict[str, str]] = [
    {"key": "interview", "title": "Интервью", "description": "Базовое интервью для профиля."},
    {"key": "mood_tracker", "title": "Трекер настроения", "description": "Ежедневные записи и аналитика."},
    {"key": "habit_tracker", "title": "Трекер привычек", "description": "Список привычек и ежедневные отметки."},
    {"key": "techniques", "title": "Техники", "description": "Подбор техник и упражнений по запросу."},
    {"key": "dialog", "title": "Диалог", "description": "Свободный диалог психологической поддержки."},
    {"key": "relationships", "title": "Отношения", "description": "Отдельный режим для отношений."},
]


async def seed_scenarios(session: AsyncSession) -> None:
    res = await session.execute(select(Scenario.key))
    existing = {r[0] for r in res.all()}
    for s in DEFAULT_SCENARIOS:
        if s["key"] in existing:
            continue
        session.add(Scenario(key=s["key"], title=s["title"], description=s["description"], enabled=True))
    await session.commit()

