from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Меню")]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Напишите сообщение или нажмите «Меню»",
    )

