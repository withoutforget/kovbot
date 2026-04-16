from __future__ import annotations

from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, ScrollingGroup, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from kov.logging import get_logger
from kov.tg.dialogs.common import get_chat_id, json_file, profile_merge
from kov.tg.dialogs.states import InterviewSG, MainMenuSG
from kov.tg.runtime import ensure_user_id, runtime


async def _ensure_questions(manager: DialogManager) -> list[dict[str, str]]:
    if manager.dialog_data.get("questions"):
        return manager.dialog_data["questions"]
    api = runtime().api
    data = await api.post("/scenarios/interview/start", {})
    questions = data["questions"]
    manager.dialog_data["questions"] = questions
    manager.dialog_data.setdefault("idx", 0)
    return questions


async def _load_view(*, user_id: str) -> dict[str, Any]:
    api = runtime().api
    return await api.get(f"/scenarios/interview/{user_id}")


async def start_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    return {"has_questions": bool(dialog_manager.dialog_data.get("questions"))}


async def question_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    questions = await _ensure_questions(dialog_manager)
    idx = int(dialog_manager.dialog_data.get("idx") or 0)
    idx = max(0, min(idx, len(questions) - 1))
    q = questions[idx]
    return {"q_text": q["text"], "progress": f"{idx + 1}/{len(questions)}"}


async def review_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    event = dialog_manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return {"summary": "—"}
    user_id = await ensure_user_id(event)
    view = await _load_view(user_id=user_id)
    answers: dict[str, str] = view.get("answers") or {}
    # Pretty, but compact
    lines = ["Ваши ответы:"]
    for k, v in answers.items():
        lines.append(f"• {k}: {v}")
    summary = "\n".join(lines).strip()
    return {"summary": summary[:3800]}


async def edit_pick_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    questions = await _ensure_questions(dialog_manager)
    items = [(q["question_key"], q["text"]) for q in questions]
    return {"items": items}


async def summary_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    event = dialog_manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return {"summary": "—"}
    user_id = await ensure_user_id(event)
    view = await _load_view(user_id=user_id)
    return {"summary": (view.get("summary") or "—")[:3800], "answers": view.get("answers") or {}}


async def on_begin_clicked(_, __, manager: DialogManager) -> None:
    manager.dialog_data.pop("questions", None)
    manager.dialog_data["idx"] = 0
    await _ensure_questions(manager)
    await manager.switch_to(InterviewSG.question)


async def on_interrupt_clicked(_, __, manager: DialogManager) -> None:
    event = manager.event
    try:
        if isinstance(event, (Message, CallbackQuery)):
            await profile_merge(event, data={"last_scenario": "interview"})
    except Exception:
        pass
    await manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)


async def on_answer_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    log = get_logger(component="tg_interview")
    text = (message.text or "").strip()
    if not text:
        return
    try:
        user_id = await ensure_user_id(message)
        questions = await _ensure_questions(manager)
        idx = int(manager.dialog_data.get("idx") or 0)
        idx = max(0, min(idx, len(questions) - 1))
        q = questions[idx]
        await runtime().api.post(
            "/scenarios/interview/answer",
            {"user_id": user_id, "question_key": q["question_key"], "answer_text": text},
        )
        idx += 1
        if idx >= len(questions):
            manager.dialog_data["idx"] = len(questions) - 1
            await manager.switch_to(InterviewSG.review)
        else:
            manager.dialog_data["idx"] = idx
            await manager.switch_to(InterviewSG.question)
    except Exception as e:
        log.error("interview_answer_failed", error=str(e))
        await message.answer("Не удалось сохранить ответ. Проверь, что API доступен.")


async def on_pick_question(
    callback: CallbackQuery, _widget: Select, manager: DialogManager, item_id: str
) -> None:
    manager.dialog_data["edit_key"] = item_id
    await manager.switch_to(InterviewSG.edit_answer)
    await callback.answer()


async def on_edit_answer_message(message: Message, _widget: MessageInput, manager: DialogManager) -> None:
    log = get_logger(component="tg_interview")
    text = (message.text or "").strip()
    if not text:
        return
    key = manager.dialog_data.get("edit_key")
    if not key:
        await manager.switch_to(InterviewSG.review)
        return
    try:
        user_id = await ensure_user_id(message)
        await runtime().api.post(
            "/scenarios/interview/answer",
            {"user_id": user_id, "question_key": key, "answer_text": text},
        )
        await manager.switch_to(InterviewSG.review)
    except Exception as e:
        log.error("interview_edit_failed", error=str(e))
        await message.answer("Не удалось сохранить изменения.")


async def on_export_clicked(_, __, manager: DialogManager) -> None:
    event = manager.event
    msg = event if isinstance(event, Message) else event.message if isinstance(event, CallbackQuery) else None
    if not msg or not isinstance(event, (Message, CallbackQuery)):
        return
    user_id = await ensure_user_id(event)
    view = await _load_view(user_id=user_id)
    doc = json_file(filename="interview.json", data=view)
    await msg.bot.send_document(chat_id=get_chat_id(manager), document=doc, caption="Интервью (экспорт)")


interview_dialog = Dialog(
    Window(
        Const(
            "Интервью\n\n"
            "Короткая серия вопросов, чтобы собрать базовую картину и использовать её для персонализации."
        ),
        Button(Const("Начать / пройти заново"), id="begin", on_click=on_begin_clicked),
        SwitchTo(Const("Посмотреть ответы"), id="view", state=InterviewSG.review),
        Button(Const("В меню"), id="to_menu", on_click=on_interrupt_clicked),
        getter=start_getter,
        state=InterviewSG.start,
    ),
    Window(
        Format("Интервью ({progress})\n\n{q_text}\n\nОтветьте сообщением."),
        MessageInput(on_answer_message),
        Button(Const("Прервать → меню"), id="interrupt", on_click=on_interrupt_clicked),
        getter=question_getter,
        state=InterviewSG.question,
    ),
    Window(
        Format("{summary}\n\nМожно отредактировать ответы или посмотреть сводку."),
        SwitchTo(Const("Редактировать"), id="edit", state=InterviewSG.edit_pick),
        SwitchTo(Const("Сводка"), id="sum", state=InterviewSG.summary),
        SwitchTo(Const("Назад"), id="back_start", state=InterviewSG.start),
        Button(Const("В меню"), id="to_menu2", on_click=on_interrupt_clicked),
        getter=review_getter,
        state=InterviewSG.review,
    ),
    Window(
        Const("Что хотите изменить?"),
        ScrollingGroup(
            Select(
                Format("{item[1]}"),
                id="q",
                item_id_getter=lambda item: item[0],
                items="items",
                on_click=on_pick_question,
            ),
            id="q_g",
            width=1,
            height=8,
        ),
        SwitchTo(Const("Назад"), id="back_review", state=InterviewSG.review),
        getter=edit_pick_getter,
        state=InterviewSG.edit_pick,
    ),
    Window(
        Const("Напишите новый ответ:"),
        MessageInput(on_edit_answer_message),
        SwitchTo(Const("Назад"), id="back_review2", state=InterviewSG.review),
        state=InterviewSG.edit_answer,
    ),
    Window(
        Format("Сводка:\n\n{summary}"),
        Button(Const("Экспорт JSON"), id="export", on_click=on_export_clicked),
        SwitchTo(Const("Назад"), id="back_review3", state=InterviewSG.review),
        Button(Const("В меню"), id="to_menu3", on_click=on_interrupt_clicked),
        getter=summary_getter,
        state=InterviewSG.summary,
    ),
)
