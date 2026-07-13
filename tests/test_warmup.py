"""Тесты подбора разминки и заминки по группам мышц."""
from app.core import warmup


def test_warmup_includes_general_and_group_specific():
    text = warmup.warmup_text(["грудь/трицепс", "ноги/ягодицы"])
    assert "Разминка" in text
    assert "суставная" in text.lower()
    # Подтянулись подсказки по груди и ногам
    assert "груд" in text.lower()
    assert "приседани" in text.lower()


def test_cooldown_includes_general_and_group_specific():
    text = warmup.cooldown_text(["пресс"])
    assert "Заминка" in text
    assert "дыхан" in text.lower()
    assert "кобры" in text.lower()


def test_empty_groups_only_general():
    text = warmup.warmup_text([])
    assert "Разминка" in text
    # Только общая часть — две строки
    assert text.count("•") == 2
