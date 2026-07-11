"""Тесты клавиатур тренировки."""
from app.keyboards import EFFORTS, effort_kb, reps_kb


def test_reps_kb_range():
    kb = reps_kb(6, 12)
    # Собираем все callback_data кнопок повторов
    reps = [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data and btn.callback_data.startswith("reps:")
    ]
    assert reps == [f"reps:{n}" for n in range(6, 13)]


def test_effort_kb_has_three_options():
    kb = effort_kb()
    codes = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert codes == [f"eff:{code}" for code, _ in EFFORTS]
