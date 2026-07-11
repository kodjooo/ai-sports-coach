"""Тесты консистентности сид-данных."""
from app.core.seed import DEFAULT_TEMPLATES, EXERCISES


def test_template_items_reference_existing_exercises():
    names = {e["name"] for e in EXERCISES}
    for tpl in DEFAULT_TEMPLATES:
        for name, _sets, _reps in tpl["items"]:
            assert name in names, f"Упражнение '{name}' отсутствует в каталоге"


def test_templates_have_weekday():
    for tpl in DEFAULT_TEMPLATES:
        assert 0 <= tpl["weekday"] <= 6
