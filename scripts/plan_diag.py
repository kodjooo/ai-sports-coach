"""Диагностика: почему у некоторых профилей план пустой/недобитый.
Печатает размер палитры и СЫРОЙ ответ модели (до сверки с каталогом)."""
import asyncio, json
import app.core.llm as llm
from app.core import catalog, usage
from app.config import settings

CASES = [
    dict(label="колено", goal="тонус и осанка", sex="ж", level="новичок",
         equip="коврик", per_day=3, note="40 лет, болит правое колено"),
    dict(label="дом гантели+резинки", goal="похудение", sex="ж", level="средний",
         equip="гантели, резинки", per_day=4, note="34 года, сбросить вес"),
]

async def diag(p):
    main = catalog.main_candidates(p["equip"], p["level"])
    warm = catalog.warmup_candidates(p["equip"])
    print(f"\n=== {p['label']}: палитра осн={len(main)}, разм={len(warm)}")
    print("   осн по группам:", end=" ")
    from collections import Counter
    print(dict(Counter(e["muscle_group"] for e in main)))
    sys_c = "test"
    # вызовем напрямую как generate_plan, но перехватим сырой ответ
    from app.core.llm import _sanitize_plan
    # копия system из llm
    import inspect, re
    src = inspect.getsource(llm.generate_plan)
    # проще: вызвать generate_plan и посмотреть в логи; здесь вызовем модель руками с тем же промптом
    per_day=p["per_day"]
    # воспроизведём user_content
    usr=(f"Цель:{p['goal']}\nПол:{p['sex']}\nУровень:{p['level']}\n"
         f"Профиль:{p['note']}\nИнвентарь:{p['equip']}\nДни:[0,2,4]\n"
         f"РОВНО {per_day} основных на день.\n\nОСНОВНЫЕ:\n{catalog.names_for_prompt(main)}\n\nРАЗМИНКА:\n{catalog.names_for_prompt(warm)}")
    plan = await llm.generate_plan(profile_summary=p["note"], goal=p["goal"], weekdays=[0,2,4],
        environment=None, equipment=p["equip"], sex=p["sex"], level=p["level"], per_day=per_day)
    print("   generate_plan вернул дней:", len(plan))
    for w in plan:
        print(f"     д{w['weekday']}: {[ (e['name'] if isinstance(e,dict) else e) for e in w['exercises']]}")

async def main():
    for p in CASES:
        await diag(p)

asyncio.run(main())
