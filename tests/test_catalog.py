"""Тесты сгенерированного каталога упражнений."""
from app.core.seed import EXERCISES


def test_catalog_is_large():
    # Каталог должен быть широким (JSON + базовые)
    assert len(EXERCISES) >= 100


def test_catalog_has_all_environments():
    envs = {e.get("environment") for e in EXERCISES}
    assert {"дом", "улица", "зал"}.issubset(envs)


def test_catalog_entries_have_required_fields():
    for e in EXERCISES[:20]:
        assert e.get("name")
        assert e.get("technique")
