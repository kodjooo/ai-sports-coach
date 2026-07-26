"""Полный пайплайн по всем фото датасета: блюдо + граммы + финальные ккал, gpt-5 vs gpt-5.1.
Автоматически сверяет граммы с истиной по ключевым словам блюда (весы/этикетка).
Запуск: docker compose exec -T bot python -u - < scripts/food_all.py"""
import asyncio, json, glob, copy, re
import app.core.llm as llm
from app.core import openfoodfacts
from app.config import settings

MODELS = ["gpt-5", "gpt-5.1"]
# истина по граммам, распознаём блюдо по ключевому слову в dish
TRUTH_RULES = [("рис", 283), ("краб", 201), ("салат с краб", 201), ("окрошк", 486), ("йогурт", 120)]

def truth_for(dish):
    d = (dish or "").lower()
    for kw, g in TRUTH_RULES:
        if kw in d:
            return g
    return None

async def full(image_url, known, model):
    a = await llm.analyze_food_photo(image_url, known=known, model=model, tag=f"fa_{model}")
    g = sum(round(i.get("grams") or 0) for i in a.get("items", []))
    dish = a.get("dish")
    a = await openfoodfacts.refine(copy.deepcopy(a))
    kcal = round((a.get("total") or {}).get("kcal") or 0)
    return dish, g, kcal

async def main():
    settings.openai_reasoning_effort = "low"
    files = sorted(glob.glob("/app/logs/foodab/*.json"))
    files = [f for f in files if "summary" not in f and "index" not in f]
    recs = [json.load(open(fp)) for fp in files]
    recs = [r for r in recs if isinstance(r, dict) and r.get("image_url")]
    print(f"фото в датасете: {len(recs)}", flush=True)
    for idx, rec in enumerate(recs):
        print(f"\n=== фото{idx} ===", flush=True)
        for model in MODELS:
            try:
                dish, g, k = await full(rec["image_url"], rec.get("known"), model)
                t = truth_for(dish)
                err = f"  Δграмм={g-t:+d} (истина {t})" if t else ""
                print(f"  {model:8}: {g}г  ФИНАЛ={k}ккал  «{dish}»{err}", flush=True)
            except Exception as e:
                print(f"  {model:8}: ERR {repr(e)[:80]}", flush=True)

asyncio.run(main())
