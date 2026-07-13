"""Inline-клавиатуры бота."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# Соответствие кода ощущения → подпись кнопки
EFFORTS = [("easy", "😀 Легко"), ("ok", "🙂 Норм"), ("hard", "😮‍💨 Тяжело")]


def main_menu() -> ReplyKeyboardMarkup:
    """Ёмкое закреплённое нижнее меню."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="▶️ Тренировка")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ---- Настройки ----

def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗓 Дни и время тренировок", callback_data="set:schedule")],
            [InlineKeyboardButton(text="📋 План недели", callback_data="set:plan")],
            [InlineKeyboardButton(text="⚖️ Записать вес", callback_data="set:weight")],
        ]
    )


# ---- Настройка расписания ----

# Пресеты дней недели по частоте (0=Пн … 6=Вс)
DAY_COMBOS: dict[int, list[list[int]]] = {
    2: [[0, 3], [1, 4], [2, 5]],
    3: [[0, 2, 4], [1, 3, 5]],
    4: [[0, 1, 3, 5], [0, 2, 4, 6]],
}
WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
# Пресеты времени (часы)
TIME_PRESETS = [7, 8, 12, 18, 20]


def freq_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{n} раза в неделю", callback_data=f"sf:{n}") for n in (2, 3)],
            [InlineKeyboardButton(text="4 раза в неделю", callback_data="sf:4")],
        ]
    )


def days_kb(freq: int) -> InlineKeyboardMarkup:
    rows = []
    for combo in DAY_COMBOS.get(freq, DAY_COMBOS[3]):
        label = "/".join(WEEKDAYS_SHORT[d] for d in combo)
        rows.append([InlineKeyboardButton(text=label, callback_data="sd:" + ",".join(map(str, combo)))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def time_kb() -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=f"{h:02d}:00", callback_data=f"st:{h}") for h in TIME_PRESETS]
    rows = [row[i : i + 3] for i in range(0, len(row), 3)]
    rows.append([InlineKeyboardButton(text="Другое время", callback_data="st:other")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
