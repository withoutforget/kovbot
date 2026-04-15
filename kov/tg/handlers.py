from __future__ import annotations

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from kov.logging import get_logger
from kov.tg.api import ApiClient
from kov.tg.states import InterviewStates, RagChatStates


def register_handlers(dp: Dispatcher, *, api_base_url: str) -> None:
    log = get_logger(component="tg_handlers")
    api = ApiClient(api_base_url)

    @dp.message(Command("start"))
    async def start(message: Message) -> None:
        await message.answer(
            "Привет! Я Kov.\n\n"
            "Команды:\n"
            "/menu — список сценариев\n"
            "/interview — интервью\n"
            "/mood — запись настроения (сегодня)\n"
            "/habits — список привычек\n"
            "/rag — задать вопрос по корпусу\n"
        )

    @dp.message(Command("menu"))
    async def menu(message: Message) -> None:
        items = await api.get("/scenarios")
        text = "Сценарии:\n" + "\n".join([f"- {s['title']} (`{s['key']}`)" for s in items])
        await message.answer(text)

    async def ensure_user(message: Message) -> str:
        data = await api.post(
            "/users/ensure",
            {
                "telegram_user_id": str(message.from_user.id),
                "timezone": "UTC",
                "language": message.from_user.language_code or "ru",
            },
        )
        return data["user_id"]

    @dp.message(Command("interview"))
    async def interview(message: Message, state: FSMContext) -> None:
        user_id = await ensure_user(message)
        start_data = await api.post("/scenarios/interview/start", {})
        await state.update_data(user_id=user_id, questions=start_data["questions"], idx=0)
        await state.set_state(InterviewStates.answering)
        q = start_data["questions"][0]
        await message.answer(f"Интервью. Вопрос 1/{len(start_data['questions'])}:\n{q['text']}")

    @dp.message(InterviewStates.answering)
    async def interview_answer(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        questions = data.get("questions") or []
        idx = int(data.get("idx") or 0)
        user_id = data["user_id"]
        if idx >= len(questions):
            await state.clear()
            await message.answer("Интервью уже завершено. /menu")
            return
        q = questions[idx]
        await api.post(
            "/scenarios/interview/answer",
            {"user_id": user_id, "question_key": q["question_key"], "answer_text": message.text or ""},
        )
        idx += 1
        if idx >= len(questions):
            view = await api.get(f"/scenarios/interview/{user_id}")
            await state.clear()
            await message.answer("Спасибо! Итоговая сводка:\n" + view["summary"])
            return
        await state.update_data(idx=idx)
        q = questions[idx]
        await message.answer(f"Вопрос {idx+1}/{len(questions)}:\n{q['text']}")

    @dp.message(Command("rag"))
    async def rag(message: Message, state: FSMContext) -> None:
        await state.set_state(RagChatStates.asking)
        await message.answer("Напишите ваш запрос — я выполню поиск по корпусу.")

    @dp.message(RagChatStates.asking)
    async def rag_query(message: Message, state: FSMContext) -> None:
        user_id = await ensure_user(message)
        try:
            result = await api.post(
                "/rag/search",
                {
                    "user_query": message.text or "",
                    "user_id": user_id,
                    "scenario_id": "dialog",
                    "language": "ru",
                    "search_profile": "quick_advice",
                },
            )
        except Exception as e:
            log.error("rag_failed", error=str(e))
            await message.answer("Ошибка поиска. Проверьте, что API поднят.")
            return
        parts = result.get("telegram_messages") or []
        for p in parts:
            await message.answer(p["text"])

    @dp.message(Command("mood"))
    async def mood(message: Message) -> None:
        user_id = await ensure_user(message)
        await api.post("/mood/entry", {"user_id": user_id, "notes": "запись из бота"})
        await message.answer("Запись настроения сохранена (черновик).")

    @dp.message(Command("habits"))
    async def habits(message: Message) -> None:
        user_id = await ensure_user(message)
        items = await api.get(f"/habits/{user_id}")
        if not items:
            await message.answer("Пока привычек нет. Добавить можно через API `POST /habits`.")
            return
        await message.answer("Привычки:\n" + "\n".join([f"- {h['title']} ({h['habit_id']})" for h in items]))

