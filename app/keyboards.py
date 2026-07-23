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
            [InlineKeyboardButton(text="📅 Дни тренировок", callback_data="set:schedule")],
            [InlineKeyboardButton(text="⏰ Время напоминаний", callback_data="set:time")],
            [InlineKeyboardButton(text="🏋 Место и инвентарь", callback_data="set:env")],
            [InlineKeyboardButton(text="🎚 Уровень подготовки", callback_data="set:level")],
            [InlineKeyboardButton(text="🔢 Упражнений в тренировке", callback_data="set:exd")],
            [InlineKeyboardButton(text="🍽 Цель по питанию", callback_data="set:ngoal")],
            [InlineKeyboardButton(text="📋 План недели", callback_data="set:plan")],
            [InlineKeyboardButton(text="⚖️ Записать вес", callback_data="set:weight")],
            [InlineKeyboardButton(text="🔄 Обновить профиль", callback_data="set:profile")],
            [InlineKeyboardButton(text="ℹ️ Что я умею", callback_data="set:help")],
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


def time_only_kb() -> InlineKeyboardMarkup:
    """Выбор только времени напоминаний (без пересборки плана)."""
    row = [InlineKeyboardButton(text=f"{h:02d}:00", callback_data=f"tmset:{h}") for h in TIME_PRESETS]
    rows = [row[i : i + 3] for i in range(0, len(row), 3)]
    rows.append([InlineKeyboardButton(text="Другое время", callback_data="tmset:other")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def warmup_done_kb() -> InlineKeyboardMarkup:
    """Кнопка перехода от разминки к упражнениям (для старого текстового фолбэка)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ К упражнениям", callback_data="wk:warmup_done")],
        ]
    )


def warmup_step_kb(last: bool) -> InlineKeyboardMarkup:
    """Пошаговая разминка: «Далее» между движениями, «К упражнениям» на последнем."""
    text = "▶️ К упражнениям" if last else "➡️ Далее"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data="wk:warm_next")]]
    )


# Чеклист инвентаря (мультивыбор). Текст сохраняется в user.equipment и парсится catalog.available_equipment.
# Порядок фиксирован — индекс используется в callback_data eq:t:<idx>.
# Метки подобраны так, чтобы их текст содержал токен из catalog._EQUIP_TOKENS.
# «Всё оборудование» раскрывает весь словарь (это не «место», а «есть всё»).
EQUIPMENT_OPTIONS: list[str] = [
    "Без инвентаря",
    "Гантели",
    "Штанга",
    "Гиря",
    "Резинки",
    "Турник",
    "Брусья",
    "Скамья",
    "Тренажёры",
    "Блок/трос",
    "Медбол",
    "Фитбол",
    "Тумба/степ",
    "TRX/петли",
    "Всё оборудование",
]


def equipment_kb(selected: set[int]) -> InlineKeyboardMarkup:
    """Чеклист инвентаря: тап переключает ✅, «Готово» завершает."""
    rows = []
    for i, label in enumerate(EQUIPMENT_OPTIONS):
        mark = "✅ " if i in selected else "▫️ "
        rows.append([InlineKeyboardButton(text=mark + label, callback_data=f"eq:t:{i}")])
    rows.append([InlineKeyboardButton(text="➡️ Готово", callback_data="eq:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cooldown_step_kb(last: bool) -> InlineKeyboardMarkup:
    """Пошаговая заминка: «Далее» между движениями, «Завершить» на последнем."""
    text = "✅ Завершить тренировку" if last else "➡️ Далее"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data="wk:cool_next")]]
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
    """Кнопка завершения после заминки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Завершить тренировку", callback_data="wk:cooldown_done")],
        ]
    )


def workout_menu() -> ReplyKeyboardMarkup:
    """Нижнее меню во время тренировки — только завершение (чтобы не начать новую)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏁 Завершить тренировку")]],
        resize_keyboard=True,
        is_persistent=True,
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
