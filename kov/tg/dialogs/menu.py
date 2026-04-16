from __future__ import annotations

from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.text import Const

from kov.tg.dialogs.states import KnowledgeBaseSG, MainMenuSG


async def on_kb_clicked(_, __, manager: DialogManager) -> None:
    await manager.start(KnowledgeBaseSG.chat, mode=StartMode.RESET_STACK)


main_menu_dialog = Dialog(
    Window(
        Const(
            "Меню\n\n"
            "Выберите режим:"
        ),
        Button(Const("Поиск по базе знаний"), id="kb", on_click=on_kb_clicked),
        state=MainMenuSG.menu,
    )
)

