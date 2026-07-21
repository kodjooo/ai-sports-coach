"""Тесты расчёта нормы калорий и БЖУ."""
from types import SimpleNamespace

from app.core import nutrition


def _user(**kw):
    base = dict(weight_kg=80, height_cm=180, age=30, sex="м", activity="средняя",
                goal="поддержание", nutrition_goal=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_norm_none_when_data_missing():
    assert nutrition.daily_norm(_user(age=None)) is None


def test_norm_reasonable_for_man():
    n = nutrition.daily_norm(_user())
    # Ориентир ~2600–2900 ккал для таких данных при средней активности
    assert 2200 < n["kcal"] < 3200
    assert n["protein"] > 0 and n["fat"] > 0 and n["carbs"] > 0


def test_goal_deficit_lower_than_maintenance():
    maint = nutrition.daily_norm(_user(goal="поддержание"))["kcal"]
    cut = nutrition.daily_norm(_user(goal="похудеть"))["kcal"]
    assert cut < maint
