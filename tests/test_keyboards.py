"""Тесты клавиатур тренировки."""
from app.keyboards import EFFORTS, effort_kb, reps_kb


def _reps(kb):
    return [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data and btn.callback_data.startswith("reps:")
    ]


def test_reps_kb_centered_on_target():
    kb = reps_kb(target=15)
    assert _reps(kb) == [f"reps:{n}" for n in range(12, 19)]


def test_reps_kb_low_target_not_below_one():
    kb = reps_kb(target=2)
    vals = [int(c.split(":")[1]) for c in _reps(kb)]
    assert min(vals) >= 1


def test_reps_kb_time_mode_gives_seconds_around_target():
    kb = reps_kb(target=40, is_time=True)
    vals = [int(c.split(":")[1]) for c in _reps(kb)]
    assert 40 in vals and 20 in vals and 70 in vals


def test_effort_kb_has_three_options():
    kb = effort_kb()
    codes = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert codes == [f"eff:{code}" for code, _ in EFFORTS]
