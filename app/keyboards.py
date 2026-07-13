"""Inline-клавиатуры бота."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# Соответствие кода ощущения → подпись кнопки
EFFORTS = [("easy", "😀 Легко"), ("ok", "🙂 Норм"), ("hard", "😮‍💨 Тяжело")]


def main_menu() -> ReplyKeyboardMarkup:
    """Закреплённое нижнее меню с возможностью свернуть."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="▶️ Начать тренировку"), KeyboardButton(text="📊 План недели")],
            [KeyboardButton(text="📈 Статистика"), KeyboardButton(text="⚖️ Записать вес")],
            [KeyboardButton(text="🔽 Свернуть меню")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def warmup_done_kb() -> InlineKeyboardMarkup:
    """Кнопка перехода от разминки к упражнениям."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="▶️ К упражнениям", callback_data="wk:warmup_done")]]
    )


def cooldown_done_kb() -> InlineKeyboardMarkup:
    """Кнопка завершения тренировки после заминки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить тренировку", callback_data="wk:cooldown_done")]]
    )


def reminder_kb() -> InlineKeyboardMarkup:
    """Кнопки утреннего напоминания."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Начать", callback_data="wk:start")],
            [InlineKeyboardButton(text="⏭ Перенести на завтра", callback_data="wk:move")],
            [InlineKeyboardButton(text="📊 План недели", callback_data="menu:plan")],
        ]
    )


def reps_kb(low: int = 6, high: int = 12) -> InlineKeyboardMarkup:
    """Кнопки выбора числа повторов + доп. действия."""
    row = [
        InlineKeyboardButton(text=str(n), callback_data=f"reps:{n}")
        for n in range(low, high + 1)
    ]
    # Разбиваем на строки по 4 кнопки
    rows = [row[i : i + 4] for i in range(0, len(row), 4)]
    rows.append(
        [
            InlineKeyboardButton(text="❓ Как правильно?", callback_data="wk:howto"),
            InlineKeyboardButton(text="🔄 Заменить", callback_data="wk:replace"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def effort_kb() -> InlineKeyboardMarkup:
    """Кнопки оценки ощущения после сета."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"eff:{code}") for code, label in EFFORTS]
        ]
    )


def replace_scope_kb() -> InlineKeyboardMarkup:
    """Выбор области замены упражнения."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Заменить только сегодня", callback_data="rep:today")],
            [InlineKeyboardButton(text="📌 Заменить в плане навсегда", callback_data="rep:forever")],
            [InlineKeyboardButton(text="↩️ Оставить", callback_data="rep:keep")],
        ]
    )
