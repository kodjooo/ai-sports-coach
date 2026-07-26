"""Тот же тест распознавания еды на нескольких моделях (low reasoning), сверка с истиной.
Запуск: docker compose exec -T bot python -u - < scripts/food_models.py"""
import asyncio, json, glob
import app.core.llm as llm
from app.config import settings

MODELS = ["gpt-5", "gpt-5.1", "gpt-5.2", "gpt-5.4", "gpt-5.6-terra"]
TRUTH = {0: None, 1: 201, 2: 120, 3: None, 4: 486}  # порядок = sorted(*.json)

async def main():
    settings.openai_reasoning_effort = "low"
    files = sorted(glob.glob("/app/logs/foodab/*.json"))
    recs = [json.load(open(fp)) for fp in files]
    for idx, rec in enumerate(recs):
        truth = TRUTH.get(idx)
        print(f"\n=== фото {idx} (истина: {truth}) ===", flush=True)
        for model in MODELS:
            try:
                a = await llm.analyze_food_photo(rec["image_url"], known=rec.get("known"),
                                                 model=model, tag=f"fm_{model}")
                t = a.get("total", {}) or {}
                g = sum(round(i.get("grams") or 0) for i in a.get("items", []))
                err = f"  Δ={g-truth:+d}г" if truth else ""
                print(f"  {model:15}: {g}г {round(t.get('kcal') or 0)}ккал  «{a.get('dish')}»{err}", flush=True)
            except Exception as e:
                print(f"  {model:15}: ERR {repr(e)[:90]}", flush=True)

asyncio.run(main())
