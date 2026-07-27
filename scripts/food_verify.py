"""Проверка стабильности калорий после P0 (медиана+кэш): gpt-5, 3 повтора, полный пайплайн.
Печатает по каждому фото повторы финальных ккал и разброс (σ).
Запуск: docker compose exec -T bot python -u - < scripts/food_verify.py"""
import asyncio, json, glob, copy, statistics
import app.core.llm as llm
from app.core import openfoodfacts
from app.config import settings

REPS = 3

async def full(image_url, known):
    a = await llm.analyze_food_photo(image_url, known=known, model="gpt-5", tag="fv")
    dish = a.get("dish")
    g = sum(round(i.get("grams") or 0) for i in a.get("items", []))
    a = await openfoodfacts.refine(copy.deepcopy(a))
    return dish, g, round((a.get("total") or {}).get("kcal") or 0)

async def main():
    settings.openai_reasoning_effort = "low"
    files = sorted(glob.glob("/app/logs/foodab/*.json"))
    files = [f for f in files if "summary" not in f and "index" not in f]
    recs = [json.load(open(fp)) for fp in files]
    recs = [r for r in recs if isinstance(r, dict) and r.get("image_url")]
    for idx, rec in enumerate(recs):
        kcals, gs, dish = [], [], None
        for _ in range(REPS):
            try:
                dish, g, k = await full(rec["image_url"], rec.get("known"))
                kcals.append(k); gs.append(g)
            except Exception as e:
                print(f"фото{idx}: ERR {repr(e)[:70]}", flush=True)
        if kcals:
            sd = round(statistics.pstdev(kcals)) if len(kcals) > 1 else 0
            spread = max(kcals) - min(kcals)
            print(f"фото{idx:2} «{(dish or '')[:32]:32}» ккал={kcals} σ={sd} разброс={spread}  граммы={gs}", flush=True)

asyncio.run(main())
