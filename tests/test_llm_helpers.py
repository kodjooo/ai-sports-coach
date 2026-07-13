"""Тесты вспомогательных функций LLM-слоя (без обращения к API)."""
from app.core import llm


def test_system_content_prepends_safety_header():
    content = llm._system_content("Персональный промпт клиента")
    assert content.startswith(llm.SAFETY_HEADER)
    assert "Персональный промпт клиента" in content


def test_system_content_fallback_to_default():
    content = llm._system_content(None)
    assert llm.SAFETY_HEADER in content
    assert llm.SYSTEM_PROMPT in content
