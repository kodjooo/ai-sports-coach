"""Мини-сравнение reasoning low vs medium: 3 профиля × 2 уровня = 6 вызовов.
Запуск: docker compose exec -T bot python -u - < scripts/plan_reasoning.py
Печатает NDJSON построчно."""
import asyncio, json, sys
import app.core.llm as llm
from app.config import settings

PROFILES = [
    dict(label="Новичок, зал, м, общая форма", goal="общая форма", sex="м", level="новичок",
         equip="всё оборудование зала", per_day=4, note="30 лет, здоров"),
    dict(label="Средний, дом (гантели+резинки), ж, похудение", goal="похудение", sex="ж", level="средний",
         equip="гантели, резинки", per_day=4, note="34 года, хочет сбросить вес"),
    dict(label="Новичок, дом без инвентаря, ж, тонус, болит колено", goal="тонус и осанка", sex="ж", level="новичок",
         equip="коврик", per_day=3, note="40 лет, болит правое колено"),
]

def compact(plan):
    return [{"weekday": w["weekday"],
             "exercises": [(e["name"] if isinstance(e, dict) else e) for e in w["exercises"]]}
            for w in plan]

async def main():
    for effort in ("low", "medium"):
        settings.openai_reasoning_effort_plan = effort  # переключаем reasoning без правки кода
        for p in PROFILES:
            try:
                plan = await llm.generate_plan(
                    profile_summary=p["note"], goal=p["goal"], weekdays=[0, 2, 4],
                    environment=None, equipment=p["equip"], sex=p["sex"],
                    level=p["level"], per_day=p["per_day"])
                row = {"effort": effort, "profile": p["label"], "plan": compact(plan)}
            except Exception as e:
                row = {"effort": effort, "profile": p["label"], "error": repr(e)[:150]}
            print(json.dumps(row, ensure_ascii=False), flush=True)
            sys.stdout.flush()

asyncio.run(main())
