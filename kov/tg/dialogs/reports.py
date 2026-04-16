from __future__ import annotations

from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.kbd import Button, ScrollingGroup, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from kov.logging import get_logger
from kov.tg.dialogs.states import MainMenuSG, ReportsSG
from kov.tg.runtime import ensure_user_id, runtime


def _label(r: dict[str, Any]) -> str:
    rt = r.get("report_type") or ""
    ps = r.get("period_start") or ""
    pe = r.get("period_end") or ""
    return f"{rt}: {ps} → {pe}".strip()


async def list_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    event = dialog_manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return {"items": []}
    user_id = await ensure_user_id(event)
    items: list[dict[str, Any]] = await runtime().api.get(f"/reports/list/{user_id}")
    dialog_manager.dialog_data["reports"] = items
    out = [(r.get("id") or "", _label(r), r) for r in items]
    return {"items": out}


async def on_pick_report(
    callback: CallbackQuery, _widget: Select, manager: DialogManager, item_id: str
) -> None:
    reports = manager.dialog_data.get("reports") or []
    selected = next((r for r in reports if (r.get("id") or "") == item_id), None)
    manager.dialog_data["selected_report_id"] = item_id
    manager.dialog_data["selected_report"] = selected or {}
    await manager.switch_to(ReportsSG.view)
    await callback.answer()


async def view_getter(dialog_manager: DialogManager, **_) -> dict[str, Any]:
    log = get_logger(component="tg_reports")
    event = dialog_manager.event
    if not isinstance(event, (Message, CallbackQuery)):
        return {"text": "—"}
    report_id = dialog_manager.dialog_data.get("selected_report_id")
    if not report_id:
        return {"text": "—"}
    try:
        data = await runtime().api.get(f"/reports/{report_id}")
        content = data.get("content") or {}
        rt = data.get("report_type") or ""
        # Pretty print a compact version for known report types
        if rt.startswith("mood_"):
            lines = [
                f"Отчёт: {rt}",
                "",
                f"Период: {content.get('period_start')} → {content.get('period_end')}",
                f"Среднее настроение: {content.get('avg_mood')}",
                "",
                "Дневные оценки:",
            ]
            for d, s in content.get("daily_scores") or []:
                lines.append(f"• {d}: {s}")
            text = "\n".join(lines).strip()
        elif rt.startswith("habits_"):
            lines = [
                f"Отчёт: {rt}",
                "",
                f"Период: {content.get('period_start')} → {content.get('period_end')}",
                "",
                "Привычки:",
            ]
            for h in content.get("habits") or []:
                lines.append(f"• {h.get('title')}: {h.get('done')}/{h.get('total')}")
            text = "\n".join(lines).strip()
        else:
            text = str(content)
        return {"text": text[:3800]}
    except Exception as e:
        log.error("report_view_failed", error=str(e))
        return {"text": "Не удалось загрузить отчёт."}


async def on_to_menu_clicked(_, __, manager: DialogManager) -> None:
    await manager.start(MainMenuSG.menu, mode=StartMode.RESET_STACK)


reports_dialog = Dialog(
    Window(
        Const("Отчёты и аналитика\n\nСписок последних отчётов:"),
        ScrollingGroup(
            Select(
                Format("{item[1]}"),
                id="r",
                items="items",
                item_id_getter=lambda item: item[0],
                on_click=on_pick_report,
            ),
            id="r_g",
            width=1,
            height=8,
        ),
        Button(Const("В меню"), id="menu", on_click=on_to_menu_clicked),
        getter=list_getter,
        state=ReportsSG.list,
    ),
    Window(
        Format("{text}"),
        SwitchTo(Const("Назад"), id="back", state=ReportsSG.list),
        Button(Const("В меню"), id="menu2", on_click=on_to_menu_clicked),
        getter=view_getter,
        state=ReportsSG.view,
    ),
)
