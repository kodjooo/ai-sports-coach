"""Наполнение справочника упражнений и стартовых шаблонов пользователя."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Exercise, TemplateItem, WorkoutTemplate

# Базовый каталог домашних упражнений
EXERCISES: list[dict] = [
    {
        "name": "Отжимания от пола",
        "muscle_group": "грудь/трицепс",
        "difficulty": 3,
        "technique": "Тело прямое, локти под 45°, опускаться до касания грудью, полностью выпрямлять руки.",
        "variations": ["от стены", "от скамьи", "с колен", "негативные"],
    },
    {
        "name": "Приседания",
        "muscle_group": "ноги/ягодицы",
        "difficulty": 2,
        "technique": "Спина прямая, колени по направлению стоп, таз отводить назад, бёдра до параллели с полом.",
        "variations": ["у стены", "с опорой", "плие", "болгарские"],
    },
    {
        "name": "Пресс (скручивания)",
        "muscle_group": "пресс",
        "difficulty": 2,
        "technique": "Поясница прижата к полу, подъём за счёт мышц живота, без рывков шеей.",
        "variations": ["обратные", "велосипед", "планка"],
    },
    {
        "name": "Планка",
        "muscle_group": "кор",
        "difficulty": 2,
        "technique": "Тело в прямую линию, таз не проваливается, живот и ягодицы в напряжении.",
        "variations": ["на коленях", "боковая", "с подъёмом ног"],
    },
]

# Стартовые дни (label, weekday 0=Пн). Наполнение — по названиям упражнений.
DEFAULT_TEMPLATES: list[dict] = [
    {
        "label": "День A",
        "weekday": 0,  # понедельник
        "items": [
            ("Отжимания от пола", 3, 8),
            ("Приседания", 3, 12),
            ("Пресс (скручивания)", 3, 15),
        ],
    },
    {
        "label": "День B",
        "weekday": 2,  # среда
        "items": [
            ("Приседания", 4, 12),
            ("Планка", 3, 40),
            ("Отжимания от пола", 3, 8),
        ],
    },
]


async def seed_exercises(db: AsyncSession) -> None:
    """Идемпотентно наполняет каталог упражнений."""
    count = await db.scalar(select(func.count()).select_from(Exercise))
    if count and count > 0:
        return
    for data in EXERCISES:
        db.add(Exercise(**data))
    await db.commit()


async def ensure_default_templates(db: AsyncSession, user_id: int) -> None:
    """Создаёт стартовые шаблоны дней, если у пользователя их ещё нет."""
    existing = await db.scalar(
        select(func.count())
        .select_from(WorkoutTemplate)
        .where(WorkoutTemplate.user_id == user_id)
    )
    if existing and existing > 0:
        return

    # Карта имя упражнения -> id
    res = await db.execute(select(Exercise))
    by_name = {ex.name: ex.id for ex in res.scalars().all()}

    for tpl in DEFAULT_TEMPLATES:
        template = WorkoutTemplate(user_id=user_id, label=tpl["label"], weekday=tpl["weekday"])
        db.add(template)
        await db.flush()  # получаем template.id
        for idx, (name, sets, reps) in enumerate(tpl["items"]):
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
