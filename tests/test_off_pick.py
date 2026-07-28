"""Тесты выбора кандидата OFF/USDA (_pick) и суточного кэша кандидатов."""
import asyncio

from app.core import openfoodfacts as off


def _c(kcal, protein=10.0, fat=5.0, carbs=20.0):
    return {"kcal": float(kcal), "protein": protein, "fat": fat, "carbs": carbs}


def test_pick_median_choice():
    # Медиана из [100, 110, 500(выброс)] после отсечения → ~105, ближайший 100 или 110
    got = off._pick([_c(100), _c(110), _c(500)], model_per100_kcal=105)
    assert got is not None
    assert got["kcal"] in (100, 110)


def test_pick_rejects_below_corridor():
    # База сильно ниже оценки модели (< 0.75×) — не доверяем (light-версии)
    assert off._pick([_c(50), _c(52), _c(48)], model_per100_kcal=200) is None


def test_pick_rejects_above_corridor():
    # База сильно выше оценки модели (> 1.6×)
    assert off._pick([_c(400), _c(410), _c(390)], model_per100_kcal=100) is None


def test_pick_filters_light_products():
    # «light/zero» (<20 ккал) отсекаются, когда модель ждёт заметную плотность
    got = off._pick([_c(5), _c(90), _c(100)], model_per100_kcal=95)
    assert got is not None
    assert got["kcal"] >= 90


def test_pick_empty_or_zero_model():
    assert off._pick([], 100) is None
    assert off._pick([_c(100)], 0) is None


def test_cached_hits_once_per_query():
    off._CAND_CACHE.clear()
    calls = {"n": 0}

    async def fake_fn(session, query):
        calls["n"] += 1
        return [_c(100)]

    async def run():
        a = await off._cached("test-src", fake_fn, None, "Гречка")
        b = await off._cached("test-src", fake_fn, None, "  гречка ")  # нормализация ключа
        return a, b

    a, b = asyncio.run(run())
    assert a == b
    assert calls["n"] == 1


def test_cached_does_not_store_empty():
    off._CAND_CACHE.clear()
    calls = {"n": 0}

    async def empty_fn(session, query):
        calls["n"] += 1
        return []

    async def run():
        await off._cached("test-src", empty_fn, None, "x")
        await off._cached("test-src", empty_fn, None, "x")

    asyncio.run(run())
    assert calls["n"] == 2  # пустая выдача не кэшируется (мог быть сетевой сбой)
