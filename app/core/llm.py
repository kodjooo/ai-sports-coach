"""Обёртка над OpenAI: диалог тренера, эмбеддинги, Vision-оценка питания."""
from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=settings.openai_api_key)

# Системная роль тренера (docs/requirements.md, раздел 7)
SYSTEM_PROMPT = (
    "Ты — персональный фитнес-тренер. Пользователь тренируется дома "
    "(отжимания, пресс, приседания), цель — снизить вес и подготовиться к "
    "турнику/брусьям. Отвечай кратко, по делу, поддерживающе, без «воды». "
    "Учитывай прогресс и прошлые заметки. Не давай медицинских диагнозов. "
    "При росте нагрузки двигайся постепенно."
)


async def chat(user_prompt: str) -> str:
    """Единичный запрос к модели рассуждений."""
    try:
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:  # не ломаем пользовательский сценарий из-за сбоя API
        logger.warning("Ошибка запроса к OpenAI chat: %s", exc)
        return "Сейчас не могу связаться с тренерским модулем, но твои результаты записаны."


async def embed(text: str) -> list[float]:
    """Эмбеддинг текста для векторной памяти."""
    resp = await client.embeddings.create(model=settings.openai_embed_model, input=text)
    return resp.data[0].embedding


async def vision_estimate_kcal(image_url: str, grams: float | None) -> str:
    """Оценка калорийности блюда по фото (Фаза 3)."""
    hint = f"Примерный вес порции: {grams} г. " if grams else ""
    try:
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"{hint}Оцени калорийность блюда на фото. "
                                "Ответь одной строкой: примерные ккал и 1 короткий совет."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("Ошибка Vision-запроса к OpenAI: %s", exc)
        return "Не удалось оценить фото. Попробуй позже."
