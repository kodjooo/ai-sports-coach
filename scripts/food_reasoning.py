"""Проверка: улучшается ли распознавание порции у дешёвых моделей при высоком reasoning.
Гоняет сохранённые фото (/app/logs/foodab) через analyze_food_photo для luna и mini
на reasoning low/medium/high. Печатает граммы/ккал для сверки с истиной.
Запуск: docker compose exec -T bot python -u - < scripts/food_reasoning.py"""
import asyncio, json, glob, sys
import app.core.llm as llm
from app.config import settings

# истина по граммам (из табло/этикетки), где известна
TRUTH = {0: None, 1: 201, 2: 120, 3: None, 4: 486}  # порядок = sorted(*.json)

async def run(image_url, known, model, effort):
    settings.openai_reasoning_effort = effort
    a = await llm.analyze_food_photo(image_url, known=known, model=model, tag=f"fr_{model}_{effort}")
    t = a.get("total", {}) or {}
    g = sum(round(i.get("grams") or 0) for i in a.get("items", []))
    return {"dish": a.get("dish"), "grams": g, "kcal": round(t.get("kcal") or 0)}

async def main():
    files = sorted(glob.glob("/app/logs/foodab/*.json"))
    for idx, fp in enumerate(files):
        rec = json.load(open(fp))
        truth = TRUTH.get(idx)
        print(f"\n=== фото {idx} (истина граммов: {truth}) ===", flush=True)
        for model in ("gpt-5.6-luna", "gpt-5-mini"):
            for effort in ("low", "high"):
                try:
                    r = await run(rec["image_url"], rec.get("known"), model, effort)
                    err = f" ошибкаΔ={r['grams']-truth:+d}г" if truth else ""
                    print(f"  {model:14} {effort:4}: {r['grams']}г {r['kcal']}ккал  «{r['dish']}»{err}", flush=True)
                except Exception as e:
                    print(f"  {model} {effort}: ERR {repr(e)[:80]}", flush=True)

asyncio.run(main())
