"""Уточнение БЖУ по базе OpenFoodFacts (бесплатно, без ключа).

Модель даёт ингредиенты и граммы + обобщённое название (query). Здесь для каждого
ингредиента ищем продукт в OFF, берём значения на 100 г и масштабируем под граммы.
Если совпадения нет или сеть недоступна — оставляем оценку модели.
"""
from __future__ import annotations

import asyncio
import logging
import statistics
import time

import aiohttp

from app.core import usda

logger = logging.getLogger(__name__)

# Кэш кандидатов из баз: (источник, query) -> (срок годности, список кандидатов).
# Один и тот же запрос в пределах суток даёт одинаковый результат → калории не «плавают»
# от прогона к прогону из-за флапа выдачи OFF/USDA, плюс меньше сетевых вызовов.
_CAND_CACHE: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_CACHE_TTL = 86400  # сутки


async def _cached(source: str, fn, session, query: str) -> list[dict]:
    key = (source, (query or "").lower().strip())
    now = time.time()
    hit = _CAND_CACHE.get(key)
    if hit and hit[0] > now:
        return hit[1]
    val = await fn(session, query)
    if val:  # кэшируем только непустую выдачу (пустую могло дать сетевым сбоем)
        _CAND_CACHE[key] = (now + _CACHE_TTL, val)
    return val

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
    """Выбирает калорийность на 100 г по МЕДИАНЕ кандидатов из базы (а не «ближайшего к
    оценке модели» — это давало порочный круг и шум прогон-к-прогону).

    Шаги: отсекаем выбросы и «light/zero»-продукты → берём медиану → возвращаем кандидата,
    ближайшего к медиане (ради согласованных Б/Ж/У). Доверяем базе только в АСИММЕТРИЧНОМ
    коридоре вокруг оценки модели: снизу жёстко (0.75×, защита от занижения калорий —
    в OFF полно обезжиренных версий), сверху мягче (1.6×)."""
    if not candidates or model_per100_kcal <= 0:
        return None
    kcals = [c["kcal"] for c in candidates if c.get("kcal", 0) > 0]
    if not kcals:
        return None
    med = statistics.median(kcals)
    # выбросы вне [0.5×; 2×] медианы + «light/zero» (меньше 20 ккал там, где ждём заметную плотность)
    trimmed = [
        c for c in candidates
        if 0.5 * med <= c["kcal"] <= 2.0 * med
        and not (c["kcal"] < 20 and model_per100_kcal >= 40)
    ]
    if not trimmed:
        trimmed = candidates
    med_k = statistics.median([c["kcal"] for c in trimmed])
    best = min(trimmed, key=lambda c: abs(c["kcal"] - med_k))
    if 0.75 * model_per100_kcal <= best["kcal"] <= 1.6 * model_per100_kcal:
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
            # Значения с этикетки — точные, не трогаем
            if it.get("source") == "label":
                continue
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
                per100 = _pick(await _cached("usda", usda.candidates, session, query), model_per100)
                source = "usda" if per100 else None
            if not per100:
                per100 = _pick(await _cached("off", _candidates, session, query), model_per100)
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
