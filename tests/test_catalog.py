"""Тесты сгенерированного каталога упражнений и палитры для тренера."""
from app.core import catalog
from app.core.seed import EXERCISES


def test_catalog_is_large():
    # Каталог должен быть широким (JSON + базовые)
    assert len(EXERCISES) >= 100


def test_catalog_has_all_environments():
    envs = {e.get("environment") for e in EXERCISES}
    # Новая схема доступности: везде / дом-зал / зал
    assert {"везде", "дом/зал", "зал"}.issubset(envs)


def test_catalog_entries_have_required_fields():
    for e in EXERCISES[:20]:
        assert e.get("name")
        assert e.get("technique")


def test_catalog_module_loaded():
    assert len(catalog.ALL) >= 500


def test_main_candidates_no_equipment():
    # Без инвентаря — только упражнения без инвентаря
    home = catalog.main_candidates("нет")
    assert home
    assert all(e["equipment"] == "без инвентаря" for e in home)


def test_main_candidates_full_gym_allows_all():
    gym = catalog.main_candidates("полный зал, всё оборудование")
    assert gym
    assert any(e["equipment"] in ("штанга", "тренажёр", "блок/трос") for e in gym)


def test_main_candidates_dumbbells_only():
    # Только гантели — вес тела + гантели, без штанги
    pool = catalog.main_candidates("гантели")
    eqs = {e["equipment"] for e in pool}
    assert "гантели" in eqs
    assert "штанга" not in eqs
    assert eqs <= {"без инвентаря", "гантели"}


def test_resolve_and_gif():
    e = catalog.ALL[0]
    hit = catalog.resolve(e["name"])
    assert hit is not None
    assert hit["gif"]
    # Нормализация регистра/пробелов
    assert catalog.resolve(f"  {e['name'].upper()} ") is not None


def test_warmup_candidates_are_stretching():
    warm = catalog.warmup_candidates("")
    assert warm
    assert all(e["kind"] == "растяжка" for e in warm)
