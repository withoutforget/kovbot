from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class InterviewStates(StatesGroup):
    answering = State()


class RagChatStates(StatesGroup):
    asking = State()

