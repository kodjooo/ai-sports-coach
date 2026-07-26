"""Полный пайплайн (analyze_food_photo + openfoodfacts.refine): финальные калории/граммы,
как их видит пользователь. gpt-5 vs gpt-5.1, 2 повтора, low reasoning.
Запуск: docker compose exec -T bot python -u - < scripts/food_full.py"""
import asyncio, json, glob, statistics, copy
import app.core.llm as llm
from app.core import openfoodfacts
from app.config import settings

MODELS = ["gpt-5", "gpt-5.1"]
REPS = 2
TRUTH_G = {0: None, 1: 201, 2: 120, 3: None, 4: 486}

async def full(image_url, known, model):
    a = await llm.analyze_food_photo(image_url, known=known, model=model, tag=f"ff_{model}")
    g = sum(round(i.get("grams") or 0) for i in a.get("items", []))
    a = await openfoodfacts.refine(copy.deepcopy(a))
    kcal = round((a.get("total") or {}).get("kcal") or 0)
    return g, kcal

async def main():
    settings.openai_reasoning_effort = "low"
    files = sorted(glob.glob("/app/logs/foodab/*.json"))
    recs = [json.load(open(fp)) for fp in files]
    for idx, rec in enumerate(recs):
        t = TRUTH_G.get(idx)
        print(f"\n=== фото{idx} (истина граммов: {t}) ===", flush=True)
        for model in MODELS:
            gs, ks = [], []
            for _ in range(REPS):
                try:
                    g, k = await full(rec["image_url"], rec.get("known"), model)
                    gs.append(g); ks.append(k)
                except Exception as e:
                    print(f"  {model}: ERR {repr(e)[:80]}", flush=True)
            gm = round(statistics.mean(gs)) if gs else 0
            km = round(statistics.mean(ks)) if ks else 0
            err = f"  Δграмм={gm-t:+d}" if t else ""
            print(f"  {model:8}: граммы≈{gm} {gs}  ФИНАЛ_ккал≈{km} {ks}{err}", flush=True)

asyncio.run(main())
