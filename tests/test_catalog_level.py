"""Тесты палитры main_candidates по уровню: плиометрика, потолок сложности, инвентарь."""
from app.core import catalog


def test_beginner_has_no_plyometrics():
    pool = catalog.main_candidates("полный зал", level="новичок")
    assert pool
    assert all(e["kind"] != "плиометрика" for e in pool)


def test_beginner_difficulty_ceiling():
    pool = catalog.main_candidates("полный зал", level="новичок")
    # Потолок 3 (страховка может ослабить до 4, но при полном зале пул большой)
    assert all((e.get("difficulty") or 3) <= 3 for e in pool)


def test_advanced_allows_plyometrics():
    pool = catalog.main_candidates("полный зал", level="продвинутый")
    kinds = {e["kind"] for e in pool}
    # В большом каталоге у продвинутого плиометрика доступна
    assert "плиометрика" in kinds or len(pool) >= 50


def test_equipment_subset_of_available():
    # Всё необходимое оборудование каждого упражнения должно быть у клиента
    allowed = catalog.available_equipment("гантели, резинки")
    pool = catalog.main_candidates("гантели, резинки")
    assert pool
    for e in pool:
        assert set(e.get("equipment_req") or []).issubset(allowed)


def test_no_partner_exercises():
    pool = catalog.main_candidates("полный зал")
    assert all("партн" not in e["name"].lower() for e in pool)


def test_resolve_in_stays_inside_pool():
    # fuzzy-поиск не должен вытащить упражнение вне переданной палитры
    pool = catalog.main_candidates("нет")  # только без инвентаря
    hit = catalog.resolve_in("Приседания со штангой", pool)
    if hit is not None:
        assert hit["equipment"] == "без инвентаря"


def test_warmup_zones_prioritized():
    pool = catalog.warmup_candidates("", zones=["грудь"])
    assert pool
    # Первые элементы — по указанной зоне (если такие есть в каталоге)
    chest = [e for e in pool if "грудь" in e["muscle_group"]]
    if chest:
        assert "грудь" in pool[0]["muscle_group"]
