"""Беспристрастная оценка распознавания еды по датасету /app/logs/foodab/*.json.
Для каждого фото: слепой vision-судья оценивает обезличенные выходы моделей (A/B/C),
плюс печатает объективные ккал/граммы для сверки с истиной (весы/этикетка).
Запуск: docker compose exec -T bot python -u - < scripts/food_judge.py
Печатает NDJSON построчно + сводку."""
import asyncio, json, os, glob, sys
from collections import defaultdict
import app.core.llm as llm

JUDGE_MODEL = "gpt-5"  # сильное зрение; выходы обезличены (A/B/C) → минимум предвзятости
LETTERS = ["A", "B", "C", "D"]

JUDGE_SYS = (
    "Ты — придирчивый эксперт-нутрициолог. На фото — блюдо (возможно, видно табло кухонных весов "
    "или этикетку с пищевой ценностью). Ниже несколько НЕЗАВИСИМЫХ автоматических разборов этого фото. "
    "Оцени КАЖДЫЙ разбор строго и объективно по 4 критериям, каждый 1–5:\n"
    "- dish: верно ли определено блюдо;\n"
    "- ingredients: полнота и точность состава;\n"
    "- portion: реалистичность веса в граммах (если на фото весы/этикетка — правильный разбор ОБЯЗАН "
    "использовать это число; кто угадывает мимо — снижай);\n"
    "- kcal: правдоподобность ккал и БЖУ для этого блюда и веса.\n"
    "Верни СТРОГО JSON: {\"<letter>\": {\"dish\":int,\"ingredients\":int,\"portion\":int,\"kcal\":int,"
    "\"comment\":str}, ..., \"best\":\"<letter>\", \"ground_truth\":str}. "
    "ground_truth — что видно на весах/этикетке (число), или \"нет\"."
)

def brief_out(a):
    t = a.get("total", {}) or {}
    return {"dish": a.get("dish"), "kcal": round(t.get("kcal") or 0),
            "grams": sum(round(i.get("grams") or 0) for i in a.get("items", [])),
            "items": [i.get("name") for i in a.get("items", [])]}

async def judge_one(rec, idx):
    models = list(rec["outputs"].keys())
    # фиксированная перестановка по индексу — воспроизводимо, но порядок разный между фото
    order = models[idx % len(models):] + models[:idx % len(models)]
    mapping = {LETTERS[i]: m for i, m in enumerate(order)}
    blocks = []
    for L, m in mapping.items():
        blocks.append(f"Разбор {L}: {json.dumps(brief_out(rec['outputs'][m]), ensure_ascii=False)}")
    user = [
        {"type": "text", "text": "Оцени разборы фото:\n" + "\n".join(blocks)},
        {"type": "image_url", "image_url": {"url": rec["image_url"]}},
    ]
    resp = await llm.usage.complete(llm.get_client(), "food_judge", model=JUDGE_MODEL,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": JUDGE_SYS}, {"role": "user", "content": user}])
    verdict = json.loads(resp.choices[0].message.content or "{}")
    return mapping, verdict

async def main():
    files = sorted(glob.glob("/app/logs/foodab/*.json"))
    print(f"Датасет: {len(files)} фото", file=sys.stderr)
    agg = defaultdict(lambda: defaultdict(list))  # model -> crit -> [scores]
    wins = defaultdict(int)
    for idx, fp in enumerate(files):
        rec = json.load(open(fp))
        try:
            mapping, verdict = await judge_one(rec, idx)
        except Exception as e:
            print(json.dumps({"file": os.path.basename(fp), "error": repr(e)[:150]}, ensure_ascii=False), flush=True)
            continue
        row = {"photo": idx, "ground_truth": verdict.get("ground_truth"),
               "models": {}, "best_model": mapping.get(verdict.get("best"))}
        for L, m in mapping.items():
            sc = verdict.get(L, {}) or {}
            for c in ("dish", "ingredients", "portion", "kcal"):
                if isinstance(sc.get(c), (int, float)):
                    agg[m][c].append(sc[c])
            b = brief_out(rec["outputs"][m])
            row["models"][m] = {"scores": {c: sc.get(c) for c in ("dish","ingredients","portion","kcal")},
                                "kcal": b["kcal"], "grams": b["grams"], "dish": b["dish"],
                                "comment": sc.get("comment")}
        if row["best_model"]:
            wins[row["best_model"]] += 1
        print(json.dumps(row, ensure_ascii=False), flush=True)
    print("\n===СВОДКА===", flush=True)
    for m in agg:
        allc = {c: (round(sum(v)/len(v), 2) if v else None) for c, v in agg[m].items()}
        flat = [x for v in agg[m].values() for x in v]
        avg = round(sum(flat)/len(flat), 2) if flat else 0
        print(f"{m}: средн={avg}/5  по критериям={allc}  побед={wins[m]}", flush=True)

asyncio.run(main())
