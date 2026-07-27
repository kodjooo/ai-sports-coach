"""A/B учёта еды ТЕКСТОМ: mini vs gpt-5 vs gpt-5.1 (полный пайплайн + refine).
Сверяем финальные калории с ориентиром, ловим систематическое занижение.
Запуск: docker compose exec -T bot python -u - < scripts/food_text_ab.py"""
import asyncio, copy
import app.core.llm as llm
from app.core import openfoodfacts
from app.config import settings

MODELS = ["gpt-5-mini", "gpt-5", "gpt-5.1"]
# (описание, ориентир ккал по нутрициологии)
MEALS = [
    ("Американо 270 мл, 1.5 чайной ложки сахара", 30),
    ("Тарелка варёного белого риса, 250 г", 325),
    ("Один банан", 105),
    ("Два бутерброда: белый хлеб, варёная колбаса, сыр", 420),
    ("Куриная грудка гриль 200 г и гречка варёная 150 г", 480),
    ("Цезарь с курицей, стандартная порция ресторана", 520),
    ("Овсянка на молоке 250 г с бананом и ложкой мёда", 450),
    ("Протеиновый батончик 60 г", 230),
]

async def run(desc, model):
    a = await llm.analyze_food_text(desc, model=model)
    a = await openfoodfacts.refine(copy.deepcopy(a))
    t = a.get("total", {}) or {}
    return round(t.get("kcal") or 0), a.get("dish")

async def main():
    settings.openai_reasoning_effort = "low"
    for desc, ref in MEALS:
        print(f"\n=== «{desc}» (ориентир ~{ref} ккал) ===", flush=True)
        for model in MODELS:
            try:
                k, dish = await run(desc, model)
                sign = "+" if k >= ref else ""
                print(f"  {model:12}: {k} ккал  ({sign}{k-ref} к ориентиру)  «{dish}»", flush=True)
            except Exception as e:
                print(f"  {model:12}: ERR {repr(e)[:70]}", flush=True)

asyncio.run(main())
