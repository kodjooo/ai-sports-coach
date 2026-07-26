"""Подтверждающее сравнение gpt-5 vs gpt-5.1 на еде: 3 повтора × 5 фото, low reasoning.
Считает среднее и разброс граммов, ошибку против истины.
Запуск: docker compose exec -T bot python -u - < scripts/food_confirm.py"""
import asyncio, json, glob, statistics
import app.core.llm as llm
from app.config import settings

MODELS = ["gpt-5", "gpt-5.1"]
REPS = 3
TRUTH = {0: None, 1: 201, 2: 120, 3: None, 4: 486}

async def one(image_url, known, model):
    a = await llm.analyze_food_photo(image_url, known=known, model=model, tag=f"fc_{model}")
    g = sum(round(i.get("grams") or 0) for i in a.get("items", []))
    return g

async def main():
    settings.openai_reasoning_effort = "low"
    files = sorted(glob.glob("/app/logs/foodab/*.json"))
    recs = [json.load(open(fp)) for fp in files]
    agg = {}  # (model,idx) -> [grams]
    for idx, rec in enumerate(recs):
        for model in MODELS:
            vals = []
            for _ in range(REPS):
                try:
                    vals.append(await one(rec["image_url"], rec.get("known"), model))
                except Exception as e:
                    print(f"фото{idx} {model}: ERR {repr(e)[:80]}", flush=True)
            agg[(model, idx)] = vals
            t = TRUTH.get(idx)
            mean = round(statistics.mean(vals)) if vals else 0
            sd = round(statistics.pstdev(vals)) if len(vals) > 1 else 0
            err = f"  ошибка_ср={mean-t:+d}г" if t else ""
            print(f"фото{idx} (истина {t}) {model:8}: повторы={vals} среднее={mean} разброс±{sd}{err}", flush=True)
    # сводка по фото с истиной
    print("\n===ИТОГ по фото с весами/этикеткой===", flush=True)
    for idx in (1, 2, 4):
        t = TRUTH[idx]
        line = f"фото{idx} (истина {t}): "
        for model in MODELS:
            v = agg[(model, idx)]
            m = round(statistics.mean(v)) if v else 0
            line += f"{model}={m}(Δ{m-t:+d})  "
        print(line, flush=True)

asyncio.run(main())
