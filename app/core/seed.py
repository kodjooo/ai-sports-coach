"""Наполнение справочника упражнений и стартовых шаблонов пользователя."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Exercise, TemplateItem, WorkoutTemplate

# Базовые упражнения для стартового плана-фолбэка (гарантированно присутствуют)
BASE_EXERCISES: list[dict] = [
    {"name": "Отжимания от пола", "muscle_group": "грудь/трицепс", "difficulty": 3,
     "environment": "дом", "equipment": "нет",
     "technique": "Тело прямое, локти под 45°, опускаться до касания грудью, полностью выпрямлять руки.",
     "variations": ["с колен", "негативные"]},
    {"name": "Приседания", "muscle_group": "ноги/ягодицы", "difficulty": 2,
     "environment": "дом", "equipment": "нет",
     "technique": "Спина прямая, колени по стопам, таз назад, бёдра до параллели с полом.",
     "variations": ["плие"]},
    {"name": "Скручивания", "muscle_group": "пресс", "difficulty": 2,
     "environment": "дом", "equipment": "нет",
     "technique": "Поясница прижата, подъём за счёт живота, без рывков шеей.",
     "variations": []},
    {"name": "Планка", "muscle_group": "кор", "difficulty": 2,
     "environment": "дом", "equipment": "нет",
     "technique": "Тело в линию, таз не проваливается, живот и ягодицы в напряжении.",
     "variations": ["на коленях", "боковая"]},
]


def _load_catalog() -> list[dict]:
    """Загружает сгенерированный каталог из JSON + базовые упражнения (дедуп по имени)."""
    path = Path(__file__).with_name("exercises.json")
    catalog: list[dict] = list(BASE_EXERCISES)
    seen = {e["name"].strip().lower() for e in catalog}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for e in data:
            key = e.get("name", "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                catalog.append(e)
    except Exception:
        pass  # если файла нет — используем только базовые
    return catalog


EXERCISES: list[dict] = _load_catalog()


# Варианты тренировочного дня (чередуются по дням недели для разнообразия)
TEMPLATE_VARIANTS: list[list[tuple[str, int, int]]] = [
    [
        ("Отжимания от пола", 3, 8),
        ("Приседания", 3, 12),
        ("Скручивания", 3, 15),
    ],
    [
        ("Приседания", 4, 12),
        ("Планка", 3, 40),
        ("Отжимания от пола", 3, 8),
    ],
]


# Колонки модели Exercise, которые можно заполнить из каталога (лишние ключи, напр. kind, игнорируем)
_EX_COLUMNS = {
    "name", "muscle_group", "difficulty", "technique", "variations",
    "environment", "equipment", "gif", "name_en", "technique_en", "howto",
}


async def seed_exercises(db: AsyncSession) -> None:
    """Идемпотентно добавляет/дополняет упражнения каталога (по названию).

    Новым — вставка; существующим без медиа — дозаполнение gif/техники/EN
    (чтобы уже засеянные ранее записи получили GIF после обновления каталога).
    """
    res = await db.execute(select(Exercise))
    existing = {ex.name: ex for ex in res.scalars().all()}
    changed = False
    for data in EXERCISES:
        clean = {k: v for k, v in data.items() if k in _EX_COLUMNS}
        ex = existing.get(clean["name"])
        if ex is None:
            db.add(Exercise(**clean))
            changed = True
        else:
            # Дозаполняем медиа/EN/howto у ранее засеянной записи
            if clean.get("gif") and not ex.gif:
                ex.gif = clean.get("gif")
                ex.name_en = ex.name_en or clean.get("name_en")
                ex.technique_en = ex.technique_en or clean.get("technique_en")
                if clean.get("technique"):
                    ex.technique = clean["technique"]
                changed = True
            # howto теперь = «ошибки + легче/тяжелее»; обновляем, если контент в каталоге изменился
            if clean.get("howto") and ex.howto != clean["howto"]:
                ex.howto = clean["howto"]
                changed = True
    if changed:
        await db.commit()


async def create_templates(db: AsyncSession, user_id: int, weekdays: list[int]) -> None:
    """Пересоздаёт план: по одному шаблону на каждый выбранный день недели.

    Варианты дней чередуются для разнообразия. Прежние шаблоны деактивируются.
    """
    # Деактивируем прежний план (пересоздание из онбординга или настроек)
    old = await db.execute(select(WorkoutTemplate).where(WorkoutTemplate.user_id == user_id))
    for tpl in old.scalars().all():
        tpl.active = False

    # Карта имя упражнения -> id
    res = await db.execute(select(Exercise))
    by_name = {ex.name: ex.id for ex in res.scalars().all()}

    for i, weekday in enumerate(sorted(weekdays)):
        variant = TEMPLATE_VARIANTS[i % len(TEMPLATE_VARIANTS)]
        template = WorkoutTemplate(user_id=user_id, label=f"День {i + 1}", weekday=weekday)
        db.add(template)
        await db.flush()  # получаем template.id
        for idx, (name, sets, reps) in enumerate(variant):
            ex_id = by_name.get(name)
            if ex_id is None:
                continue
            db.add(
                TemplateItem(
                    template_id=template.id,
                    exercise_id=ex_id,
                    target_sets=sets,
                    target_reps=reps,
                    order_idx=idx,
                )
            )
    await db.commit()
