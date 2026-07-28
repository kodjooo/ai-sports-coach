"""Тесты openfoodfacts.refine: калорийность на 100 г берётся из базы (медиана кандидатов),
позиции с source=label не трогаются, total пересчитывается. Сеть/USDA замоканы."""
import asyncio

import pytest

from app.core import openfoodfacts as off


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    off._CAND_CACHE.clear()
    # USDA выключаем — тестируем OFF-ветку
    monkeypatch.setattr(off.usda, "enabled", lambda: False)

    async def fake_candidates(session, query):
        # для «rice» — реалистичный разброс с медианой ~130 ккал/100 г
        if "rice" in (query or "").lower():
            return [
                {"kcal": 130, "protein": 2.7, "fat": 0.3, "carbs": 28},
                {"kcal": 120, "protein": 2.5, "fat": 0.3, "carbs": 26},
                {"kcal": 140, "protein": 2.9, "fat": 0.4, "carbs": 30},
            ]
        return []
    monkeypatch.setattr(off, "_candidates", fake_candidates)


def test_refine_uses_db_median_and_recomputes_total():
    analysis = {
        "items": [
            {"name": "рис", "query": "boiled rice", "grams": 200, "kcal": 300,
             "protein": 5, "fat": 1, "carbs": 60},  # модель ~150 ккал/100 г
            {"name": "йогурт", "source": "label", "grams": 120, "kcal": 100,
             "protein": 4, "fat": 2, "carbs": 16},  # с этикетки — не трогаем
        ],
        "total": {"kcal": 400, "protein": 9, "fat": 3, "carbs": 76},
    }
    res = _run(off.refine(analysis))
    rice, yog = res["items"]
    # рис: медиана базы 130 ккал/100 г × 200 г = 260, source стал off
    assert rice["kcal"] == 260
    assert rice["source"] == "off"
    # йогурт с этикетки не изменился
    assert yog["kcal"] == 100 and yog.get("source") == "label"
    # total пересчитан как сумма позиций
    assert res["total"]["kcal"] == 360


def test_refine_no_match_keeps_model_estimate():
    analysis = {
        "items": [{"name": "борщ", "query": "unknown dish xyz", "grams": 300, "kcal": 250}],
        "total": {"kcal": 250},
    }
    res = _run(off.refine(analysis))
    # нет совпадений в базе → оценка модели остаётся, source не проставлен как база
    assert res["items"][0]["kcal"] == 250
    assert res["items"][0].get("source") not in ("off", "usda")


def test_cache_avoids_second_network_call(monkeypatch):
    calls = {"n": 0}

    async def counting(session, query):
        calls["n"] += 1
        return [{"kcal": 130, "protein": 2, "fat": 0, "carbs": 28}]
    monkeypatch.setattr(off, "_candidates", counting)
    off._CAND_CACHE.clear()

    async def scenario():
        a = {"items": [{"name": "рис", "query": "rice", "grams": 100, "kcal": 150}], "total": {}}
        await off.refine(a)
        b = {"items": [{"name": "рис", "query": "rice", "grams": 200, "kcal": 300}], "total": {}}
        await off.refine(b)
    _run(scenario())
    assert calls["n"] == 1  # второй одинаковый query взят из кэша
