"""Сборка контекста для GPT-4: точные факты (Postgres) + память (Chroma)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import progress, vector


async def build_context(db: AsyncSession, user_id: int, query_text: str) -> tuple[str, str]:
    """Возвращает (факты, память) для подстановки в промпт."""
    facts = await progress.build_facts(db, user_id)
    memory_docs = await vector.query_memory(user_id, query_text)
    memory = "\n".join(f"- {d}" for d in memory_docs) if memory_docs else "нет заметок"
    return facts, memory


def feedback_prompt(facts: str, memory: str, today: str) -> str:
    """User-промпт для анализа после тренировки."""
    return (
        f"ФАКТЫ (последние тренировки):\n{facts}\n\n"
        f"ПАМЯТЬ (заметки из истории):\n{memory}\n\n"
        f"СЕГОДНЯ:\n{today}\n\n"
        "Задача: дай короткий фидбек (2–4 предложения) и предложи параметры "
        "на следующую тренировку этого типа."
    )


def chat_prompt(facts: str, memory: str, question: str) -> str:
    """User-промпт для свободного вопроса тренеру."""
    return (
        f'ВОПРОС: "{question}"\n\n'
        f"ФАКТЫ:\n{facts}\n\n"
        f"ПАМЯТЬ:\n{memory}\n\n"
        "Ответь как тренер. Если просят замену — предложи 1–2 варианта "
        "с учётом уровня и коротко объясни технику."
    )
