"""Расчёт дневной нормы калорий и БЖУ (Миффлин–Сан-Жеор)."""
from __future__ import annotations

from app.core.models import User

# Коэффициенты активности (ключ → множитель к BMR)
ACTIVITY_FACTORS: dict[str, float] = {
    "низкая": 1.2,     # сидячий образ жизни
    "лёгкая": 1.375,   # 1–3 тренировки в неделю
    "средняя": 1.55,   # 3–5 тренировок
    "высокая": 1.725,  # 6–7 тренировок / физ. работа
}
# Про образ жизни в целом (без учёта тренировок — их считаем отдельно)
ACTIVITY_LABELS: list[tuple[str, str]] = [
    ("низкая", "🪑 Сидячий (мало движения за день)"),
    ("лёгкая", "🚶 Немного хожу (лёгкая активность)"),
    ("средняя", "🏃 Активный день / на ногах"),
    ("высокая", "🔥 Физический труд / много движения"),
]


# Явные режимы питания
NUTRITION_MODES: dict[str, tuple[float, str]] = {
    "похудение": (0.85, "дефицит 15%"),
    "поддержание": (1.0, "поддержание"),
    "набор": (1.10, "профицит 10%"),
}
NUTRITION_LABELS: list[tuple[str, str]] = [
    ("похудение", "📉 Похудение"),
    ("поддержание", "⚖️ Поддержание"),
    ("набор", "📈 Набор массы"),
]


def _goal_factor(goal: str | None) -> float:
    """Поправка калорий под цель (фолбэк, если режим явно не выбран)."""
    g = (goal or "").lower()
    if any(k in g for k in ("похуд", "сброс", "жир", "снизить вес", "снижение")):
        return 0.85
    if any(k in g for k in ("набор", "масса", "мышц", "поправ")):
        return 1.10
    return 1.0


def mode_of(user: User) -> tuple[float, str]:
    """Возвращает (коэффициент, подпись) режима питания пользователя."""
    if user.nutrition_goal in NUTRITION_MODES:
        return NUTRITION_MODES[user.nutrition_goal]
    factor = _goal_factor(user.goal)
    label = {0.85: "дефицит 15%", 1.10: "профицит 10%"}.get(factor, "поддержание")
    return factor, label


def daily_norm(user: User) -> dict | None:
    """Возвращает {kcal, protein, fat, carbs} или None, если данных не хватает."""
    if not (user.weight_kg and user.height_cm and user.age and user.sex):
        return None
    weight = float(user.weight_kg)
    height = float(user.height_cm)
    age = int(user.age)
    s = 5 if str(user.sex).lower().startswith("м") else -161
    bmr = 10 * weight + 6.25 * height - 5 * age + s
    factor = ACTIVITY_FACTORS.get(user.activity or "средняя", 1.55)
    goal_factor, _ = mode_of(user)
    tdee = bmr * factor * goal_factor

    kcal = round(tdee)
    protein = round(1.8 * weight)          # г
    fat = round(0.25 * kcal / 9)           # 25% калорий из жиров
    carbs = round((kcal - protein * 4 - fat * 9) / 4)
    return {"kcal": kcal, "protein": protein, "fat": max(fat, 0), "carbs": max(carbs, 0)}
