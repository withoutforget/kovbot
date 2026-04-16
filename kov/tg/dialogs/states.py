from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MainMenuSG(StatesGroup):
    menu = State()


class KnowledgeBaseSG(StatesGroup):
    chat = State()

