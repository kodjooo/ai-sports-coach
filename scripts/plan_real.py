"""Валидация РЕАЛЬНОЙ llm.generate_plan на 5 профилях (round 4).
Запуск: docker compose exec -T bot python - < scripts/plan_real.py
Выводит JSON между ===REAL=== для судьи."""
import asyncio, json
import app.core.llm as llm
from app.core import catalog

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


async def main():
    res = []
    for p in PROFILES:
        try:
            plan = await llm.generate_plan(
                profile_summary=p["note"], goal=p["goal"], weekdays=[0, 2, 4],
                environment=None, equipment=p["equip"], sex=p["sex"],
                level=p["level"], per_day=p["per_day"],
            )
            res.append({"profile": p["label"], "plan": plan})
        except Exception as e:
            res.append({"profile": p["label"], "error": repr(e)[:200]})
    print("===REAL===")
    print(json.dumps(res, ensure_ascii=False))


asyncio.run(main())
