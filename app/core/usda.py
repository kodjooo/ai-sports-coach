"""Уточнение БЖУ по USDA FoodData Central — точная база генерик-продуктов.

Активно только при заданном USDA_API_KEY. Значения приводятся к 100 г (типы данных
Foundation/SR Legacy/Survey хранят нутриенты на 100 г).
"""
from __future__ import annotations

import logging

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
_HEADERS = {"Accept": "application/json"}


def enabled() -> bool:
    return bool(settings.usda_api_key)


def _extract(food: dict) -> dict | None:
    """Достаёт ккал/Б/Ж/У на 100 г из записи USDA (энергия — ккал или кДж→ккал)."""
    vals: dict[str, float] = {}
    kj: float | None = None
    for n in food.get("foodNutrients", []):
        name = (n.get("nutrientName") or "").lower()
        unit = (n.get("unitName") or "").lower()
        value = n.get("value")
        if value is None:
            continue
        if "energy" in name and unit == "kcal" and "kcal" not in vals:
            vals["kcal"] = float(value)
        elif "energy" in name and unit == "kj" and kj is None:
            kj = float(value)
        elif name == "protein":
            vals["protein"] = float(value)
        elif "total lipid" in name or name == "fat":
            vals["fat"] = float(value)
        elif "carbohydrate" in name:
            vals["carbs"] = float(value)
    if "kcal" not in vals:
        if kj is None:
            return None
        vals["kcal"] = round(kj / 4.184)  # кДж → ккал
    return {
        "kcal": vals["kcal"],
        "protein": vals.get("protein", 0.0),
        "fat": vals.get("fat", 0.0),
        "carbs": vals.get("carbs", 0.0),
    }


async def candidates(session: aiohttp.ClientSession, query: str, n: int = 10) -> list[dict]:
    if not query or not enabled():
        return []
    params = {
        "query": query,
        "api_key": settings.usda_api_key,
        "pageSize": n,
        "dataType": "SR Legacy,Survey (FNDDS),Foundation",
    }
    try:
        async with session.get(_URL, params=params, headers=_HEADERS) as r:
            if r.status != 200:
                return []
            data = await r.json(content_type=None)
    except Exception as exc:
        logger.warning("USDA запрос не удался (%s): %s", query, exc)
        return []
    out: list[dict] = []
    for food in data.get("foods", []):
        row = _extract(food)
        if row:
            out.append(row)
    return out
