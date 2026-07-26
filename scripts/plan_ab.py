"""A/B стабильности баланса: luna vs gpt-5.1, 5 профилей × N повторов.
Запуск: docker compose exec -T bot python - < scripts/plan_ab.py
Выводит JSON между ===AB=== : [{model, profile, rep, plan}]."""
import asyncio, json
import app.core.llm as llm

MODELS = ["gpt-5.6-luna", "gpt-5.1"]
REPS = 3
PROFILES = [
    dict(label="Новичок, зал, м, общая форма", goal="общая форма", sex="м", level="новичок",
         equip="всё оборудование зала", per_day=4, note="30 лет, здоров"),
    dict(label="Средний, дом (гантели+резинки), ж, похудение", goal="похудение", sex="ж", level="средний",
         equip="гантели, резинки", per_day=4, note="34 года, хочет сбросить вес"),
    dict(label="Продвинутый, зал, м, масса", goal="набор мышечной массы", sex="м", level="продвинутый",
         equip="всё оборудование зала", per_day=5, note="28 лет, 3 года стажа"),
    dict(label="Новичок, дом без инвентаря, ж, тонус, болит колено", goal="тонус и осанка", sex="ж", level="новичок",
         equip="коврик", per_day=3, note="40 лет, болит правое колено"),
    dict(label="Средний, улица турник/брусья, м, рельеф", goal="подтянуться и рельеф", sex="м", level="средний",
         equip="турник, брусья", per_day=4, note="26 лет"),
]

def compact(plan):
    return [{"weekday": w["weekday"],
             "exercises": [(e["name"] if isinstance(e, dict) else e) for e in w["exercises"]]}
            for w in plan]

async def main():
    import sys
    for model in MODELS:
        for p in PROFILES:
            for rep in range(REPS):
                try:
                    plan = await llm.generate_plan(
                        profile_summary=p["note"], goal=p["goal"], weekdays=[0, 2, 4],
                        environment=None, equipment=p["equip"], sex=p["sex"],
                        level=p["level"], per_day=p["per_day"], model=model)
                    row = {"model": model, "profile": p["label"], "rep": rep, "plan": compact(plan)}
                except Exception as e:
                    row = {"model": model, "profile": p["label"], "rep": rep, "error": repr(e)[:150]}
                # NDJSON построчно с flush — держит SSH живым и сохраняет частичные результаты
                print(json.dumps(row, ensure_ascii=False), flush=True)
                sys.stdout.flush()

asyncio.run(main())
