"""Тесты клавиатур расписания."""
from app.keyboards import DAY_COMBOS, days_kb, freq_kb, time_kb


def test_freq_kb_has_options():
    codes = [b.callback_data for row in freq_kb().inline_keyboard for b in row]
    assert "sf:2" in codes and "sf:3" in codes and "sf:4" in codes


def test_days_kb_matches_frequency():
    for freq, combos in DAY_COMBOS.items():
        kb = days_kb(freq)
        rows = [b.callback_data for row in kb.inline_keyboard for b in row]
        assert len(rows) == len(combos)
        # Число дней в каждом пресете равно частоте
        for combo in combos:
            assert len(combo) == freq


def test_time_kb_has_presets_and_other():
    codes = [b.callback_data for row in time_kb().inline_keyboard for b in row]
    assert "st:8" in codes
    assert "st:other" in codes
