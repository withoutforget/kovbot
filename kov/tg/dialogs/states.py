from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MainMenuSG(StatesGroup):
    menu = State()
    scenarios = State()
    reports = State()
    data = State()
    reminders = State()
    timezone = State()


class KnowledgeBaseSG(StatesGroup):
    chat = State()


class InterviewSG(StatesGroup):
    start = State()
    question = State()
    review = State()
    edit_pick = State()
    edit_answer = State()
    summary = State()


class MoodSG(StatesGroup):
    menu = State()
    q_score = State()
    q_notes = State()
    q_down = State()
    q_up = State()
    history_list = State()
    history_view = State()
    weekly = State()
    monthly = State()
    settings = State()
    set_time = State()


class TechniquesSG(StatesGroup):
    ask = State()
    suggestions = State()
    detail = State()


class SupportChatSG(StatesGroup):
    chat = State()


class HabitsSG(StatesGroup):
    menu = State()
    list = State()
    detail = State()
    add_title = State()
    add_desc = State()
    edit_title = State()
    edit_desc = State()
    today_pick = State()
    today_done = State()
    log_helped = State()
    log_hindered = State()
    weekly = State()
    monthly = State()
    settings = State()
    set_time = State()


class ExportSG(StatesGroup):
    menu = State()
    export = State()


class ReportsSG(StatesGroup):
    list = State()
    view = State()


class DataSG(StatesGroup):
    menu = State()
    interview = State()
    mood_list = State()
    mood_view = State()
    habits_list = State()
    habit_view = State()
    habit_logs = State()
    habit_log_view = State()
    dialogs_list = State()
    dialog_view = State()
