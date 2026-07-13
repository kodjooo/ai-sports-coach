"""Тесты консистентности сид-данных."""
from app.core.seed import EXERCISES, TEMPLATE_VARIANTS


def test_variant_items_reference_existing_exercises():
    names = {e["name"] for e in EXERCISES}
    for variant in TEMPLATE_VARIANTS:
        for name, _sets, _reps in variant:
            assert name in names, f"Упражнение '{name}' отсутствует в каталоге"


def test_variants_not_empty():
    assert TEMPLATE_VARIANTS
    for variant in TEMPLATE_VARIANTS:
        assert len(variant) >= 1
