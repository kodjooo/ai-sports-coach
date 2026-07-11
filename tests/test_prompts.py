"""Тесты сборки промптов для LLM."""
from app.core import context as ctx


def test_feedback_prompt_contains_sections():
    p = ctx.feedback_prompt("факты", "память", "сегодня")
    assert "ФАКТЫ" in p and "ПАМЯТЬ" in p and "СЕГОДНЯ" in p
    assert "факты" in p and "память" in p and "сегодня" in p


def test_chat_prompt_contains_question():
    p = ctx.chat_prompt("ф", "п", "можно заменить упражнение?")
    assert "можно заменить упражнение?" in p
    assert "ФАКТЫ" in p and "ПАМЯТЬ" in p
