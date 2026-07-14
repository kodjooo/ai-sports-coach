"""Уточнение БЖУ по базе OpenFoodFacts (бесплатно, без ключа).

Модель даёт ингредиенты и граммы + обобщённое название (query). Здесь для каждого
ингредиента ищем продукт в OFF, берём значения на 100 г и масштабируем под граммы.
Если совпадения нет или сеть недоступна — оставляем оценку модели.
"""
from __future__ import annotations

import asyncio
import logging

import aiohttp

from app.core import usda

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
_HEADERS = {
    "User-Agent": "ai-sports-coach/1.0 (nutrition assistant)",
    "Accept": "application/json",
}
_TIMEOUT = aiohttp.ClientTimeout(total=8)


async def _candidates(session: aiohttp.ClientSession, query: str, n: int = 6) -> list[dict]:
    """Возвращает список кандидатов {kcal,protein,fat,carbs на 100 г} из OFF."""
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": n,
        "fields": "product_name,nutriments",
    }
    data = None
    for attempt in range(2):  # одна повторная попытка при флапе эндпоинта
        try:
            async with session.get(_SEARCH_URL, params=params, headers=_HEADERS) as r:
                if r.status != 200:
                    raise RuntimeError(f"status {r.status}")
                data = await r.json(content_type=None)
            break
        except Exception as exc:
            if attempt == 0:
                await asyncio.sleep(0.4)
                continue
            logger.warning("OFF запрос не удался (%s): %s", query, exc)
            return []
    if not data:
        return []

    out: list[dict] = []
    for p in data.get("products") or []:
        nut = p.get("nutriments", {})
        kcal100 = nut.get("energy-kcal_100g")
        if kcal100 in (None, ""):
            continue
        try:
            out.append(
                {
                    "kcal": float(kcal100),
                    "protein": float(nut.get("proteins_100g") or 0),
                    "fat": float(nut.get("fat_100g") or 0),
                    "carbs": float(nut.get("carbohydrates_100g") or 0),
                }
            )
        except (TypeError, ValueError):
            continue
    return out


def _pick(candidates: list[dict], model_per100_kcal: float) -> dict | None:
    """Выбирает кандидата, чья калорийность ближе всего к оценке модели,
    и только если он в разумном коридоре (0.6–1.6× от оценки)."""
    if not candidates or model_per100_kcal <= 0:
        return None
    best = min(candidates, key=lambda c: abs(c["kcal"] - model_per100_kcal))
    if 0.6 * model_per100_kcal <= best["kcal"] <= 1.6 * model_per100_kcal:
        return best
    return None


async def refine(analysis: dict) -> dict:
    """Уточняет БЖУ ингредиентов по OFF и пересчитывает total. Мутирует и возвращает analysis."""
    items = analysis.get("items") or []
    if not items:
        return analysis

    refined_any = False
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        for it in items:
            grams = it.get("grams")
            model_kcal = it.get("kcal")
            if not grams or not model_kcal:
                continue
            f = float(grams) / 100.0
            model_per100 = float(model_kcal) / f  # калорийность на 100 г по оценке модели
            query = it.get("query") or it.get("name") or ""

            # Сначала USDA (точнее для генерик-еды), затем OFF (упакованные продукты)
            source = None
            per100 = None
            if usda.enabled():
                per100 = _pick(await usda.candidates(session, query), model_per100)
                source = "usda" if per100 else None
            if not per100:
                per100 = _pick(await _candidates(session, query), model_per100)
                source = "off" if per100 else None
            if not per100:
                continue  # нет надёжного совпадения — оставляем оценку модели

            it["kcal"] = round(per100["kcal"] * f)
            it["protein"] = round(per100["protein"] * f, 1)
            it["fat"] = round(per100["fat"] * f, 1)
            it["carbs"] = round(per100["carbs"] * f, 1)
            it["source"] = source
            refined_any = True

    if refined_any:
        analysis["total"] = {
            "kcal": round(sum(i.get("kcal") or 0 for i in items)),
            "protein": round(sum(i.get("protein") or 0 for i in items), 1),
            "fat": round(sum(i.get("fat") or 0 for i in items), 1),
            "carbs": round(sum(i.get("carbs") or 0 for i in items), 1),
        }
    return analysis
