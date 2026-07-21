"""Inline-клавиатуры бота."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# Соответствие кода ощущения → подпись кнопки
EFFORTS = [("easy", "😀 Легко"), ("ok", "🙂 Норм"), ("hard", "😮‍💨 Тяжело")]


def main_menu() -> ReplyKeyboardMarkup:
    """Ёмкое закреплённое нижнее меню."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="▶️ Тренировка"), KeyboardButton(text="🍎 Питание")],
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
            [InlineKeyboardButton(text="🏋 Место и инвентарь", callback_data="set:env")],
            [InlineKeyboardButton(text="🔢 Упражнений в тренировке", callback_data="set:exd")],
            [InlineKeyboardButton(text="🍽 Цель по питанию", callback_data="set:ngoal")],
            [InlineKeyboardButton(text="📋 План недели", callback_data="set:plan")],
            [InlineKeyboardButton(text="⚖️ Записать вес", callback_data="set:weight")],
            [InlineKeyboardButton(text="♻️ Сбросить историю", callback_data="set:reset")],
        ]
    )


def reset_confirm_kb() -> InlineKeyboardMarkup:
    """Подтверждение полного сброса."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚠️ Да, сбросить всё", callback_data="reset:yes")],
            [InlineKeyboardButton(text="↩️ Отмена", callback_data="reset:no")],
        ]
    )


# Варианты среды тренировок
ENVIRONMENTS = [("дом", "🏠 Дом"), ("улица", "🌳 Улица"), ("зал", "🏋 Зал"), ("микс", "🔀 Микс")]


def env_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"env:{code}")]
            for code, label in ENVIRONMENTS
        ]
    )


def sex_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="♂️ Мужской", callback_data="sex:м"),
                InlineKeyboardButton(text="♀️ Женский", callback_data="sex:ж"),
            ]
        ]
    )


LEVELS = [("новичок", "🌱 Новичок"), ("средний", "💪 Средний"), ("продвинутый", "🏆 Продвинутый")]


def level_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"lvl:{code}")]
            for code, label in LEVELS
        ]
    )


def exercises_count_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{n} упражнения" if n < 5 else f"{n} упражнений",
                                  callback_data=f"exd:{n}") for n in (3, 4, 5)]
        ]
    )


def nutrition_goal_kb() -> InlineKeyboardMarkup:
    from app.core.nutrition import NUTRITION_LABELS

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"ngoal:{code}")]
            for code, label in NUTRITION_LABELS
        ]
    )


def activity_kb() -> InlineKeyboardMarkup:
    from app.core.nutrition import ACTIVITY_LABELS

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"actlvl:{code}")]
            for code, label in ACTIVITY_LABELS
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
    """Кнопки разминки: подробное объяснение и переход к упражнениям."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❓ Как делать разминку", callback_data="wk:warmup_info")],
            [InlineKeyboardButton(text="▶️ К упражнениям", callback_data="wk:warmup_done")],
        ]
    )


def confirm_action_kb() -> InlineKeyboardMarkup:
    """Подтверждение предложенного тренером изменения."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Применить", callback_data="act:apply"),
                InlineKeyboardButton(text="↩️ Отменить", callback_data="act:cancel"),
            ]
        ]
    )


def cooldown_done_kb() -> InlineKeyboardMarkup:
    """Кнопки заминки: подробное объяснение и завершение."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❓ Как делать заминку", callback_data="wk:cooldown_info")],
            [InlineKeyboardButton(text="✅ Завершить тренировку", callback_data="wk:cooldown_done")],
        ]
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


def reps_kb(target: int | None = None, is_time: bool = False) -> InlineKeyboardMarkup:
    """Кнопки ввода результата подхода.

    Повторы — диапазон вокруг цели; «временные» упражнения — секунды вокруг цели.
    """
    if is_time:
        base = target or 30
        values = sorted({max(5, base + d) for d in (-20, -10, 0, 10, 20, 30)})
        row = [InlineKeyboardButton(text=f"{v}с", callback_data=f"reps:{v}") for v in values]
    else:
        t = target or 8
        low = max(1, t - 3)
        row = [
            InlineKeyboardButton(text=str(n), callback_data=f"reps:{n}")
            for n in range(low, t + 4)
        ]
    # Разбиваем на строки по 4 кнопки
    rows = [row[i : i + 4] for i in range(0, len(row), 4)]
    rows.append([InlineKeyboardButton(text="✏️ Другое число", callback_data="wk:manual")])
    rows.append(
        [
            InlineKeyboardButton(text="❓ Как правильно?", callback_data="wk:howto"),
            InlineKeyboardButton(text="🔄 Заменить", callback_data="wk:replace"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="⏭ Пропустить подход", callback_data="wk:skipset"),
            InlineKeyboardButton(text="⏭⏭ Упражнение", callback_data="wk:skipex"),
        ]
    )
    rows.append([InlineKeyboardButton(text="🏁 Завершить тренировку", callback_data="wk:finishask")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def finish_confirm_kb() -> InlineKeyboardMarkup:
    """Досрочное завершение тренировки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Завершить и сохранить", callback_data="wk:finish_save")],
            [InlineKeyboardButton(text="🗑 Отменить (сбросить прогресс)", callback_data="wk:finish_discard")],
            [InlineKeyboardButton(text="↩️ Продолжить тренировку", callback_data="wk:finish_cont")],
        ]
    )


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
