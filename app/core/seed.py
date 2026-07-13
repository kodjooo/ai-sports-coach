"""Наполнение справочника упражнений и стартовых шаблонов пользователя."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Exercise, TemplateItem, WorkoutTemplate

# Каталог домашних упражнений (расширенный)
EXERCISES: list[dict] = [
    # Грудь / плечи / трицепс
    {"name": "Отжимания от пола", "muscle_group": "грудь/трицепс", "difficulty": 3,
     "technique": "Тело прямое, локти под 45°, опускаться до касания грудью, полностью выпрямлять руки.",
     "variations": ["с колен", "негативные"]},
    {"name": "Отжимания от стены", "muscle_group": "грудь/плечи", "difficulty": 1,
     "technique": "Руки на стене чуть шире плеч, корпус прямой, сгибай локти и мягко возвращайся.",
     "variations": []},
    {"name": "Отжимания от стола", "muscle_group": "грудь/плечи", "difficulty": 2,
     "technique": "Руки на устойчивой опоре, тело прямое, опускайся к краю опоры под контролем.",
     "variations": []},
    {"name": "Обратные отжимания от стула", "muscle_group": "трицепс", "difficulty": 3,
     "technique": "Руки на краю стула за спиной, опускай таз сгибая локти назад, не разводя в стороны.",
     "variations": []},
    # Ноги / ягодицы / задняя цепь
    {"name": "Приседания", "muscle_group": "ноги/ягодицы", "difficulty": 2,
     "technique": "Спина прямая, колени по стопам, таз назад, бёдра до параллели с полом.",
     "variations": ["плие"]},
    {"name": "Присед к стулу", "muscle_group": "ноги/ягодицы", "difficulty": 1,
     "technique": "Садись до касания стула и вставай; колени по носкам, стопа на полу.",
     "variations": []},
    {"name": "Выпады назад", "muscle_group": "ноги/ягодицы", "difficulty": 3,
     "technique": "Шаг назад длинный, переднее колено над стопой, корпус вертикально.",
     "variations": ["статические", "болгарские"]},
    {"name": "Ягодичный мост", "muscle_group": "ягодицы/задняя цепь", "difficulty": 2,
     "technique": "Дави пятками, поднимай таз, рёбра вниз, вверху сжимай ягодицы.",
     "variations": ["на одной ноге"]},
    {"name": "Бедренный шарнир у стены", "muscle_group": "задняя цепь/спина", "difficulty": 2,
     "technique": "Таз назад к стене, спина нейтральна, лёгкий наклон корпуса вперёд.",
     "variations": []},
    {"name": "Подъёмы на носки", "muscle_group": "голень", "difficulty": 1,
     "technique": "Поднимайся на носки максимально высоко, пауза вверху, медленно вниз.",
     "variations": ["на одной ноге"]},
    # Кор / пресс / спина
    {"name": "Планка", "muscle_group": "кор", "difficulty": 2,
     "technique": "Тело в линию, таз не проваливается, живот и ягодицы в напряжении.",
     "variations": ["на коленях", "боковая"]},
    {"name": "Боковая планка", "muscle_group": "кор", "difficulty": 3,
     "technique": "Опора на предплечье, тело в линию, таз вверх, не заваливайся.",
     "variations": ["на колене"]},
    {"name": "Bird-dog", "muscle_group": "кор/спина", "difficulty": 2,
     "technique": "Из упора на четвереньках тяни противоположные руку и ногу, таз ровно, рёбра вниз.",
     "variations": []},
    {"name": "Dead bug", "muscle_group": "кор", "difficulty": 2,
     "technique": "Лёжа на спине опускай противоположные руку и ногу, поясница прижата к полу.",
     "variations": []},
    {"name": "Скручивания", "muscle_group": "пресс", "difficulty": 2,
     "technique": "Поясница прижата, подъём за счёт живота, без рывков шеей.",
     "variations": []},
    {"name": "Обратные скручивания", "muscle_group": "пресс", "difficulty": 2,
     "technique": "Подтягивай колени к груди, отрывая таз, опускай медленно.",
     "variations": []},
    {"name": "Велосипед", "muscle_group": "пресс", "difficulty": 2,
     "technique": "Поочерёдно тяни локоть к противоположному колену, поясница прижата.",
     "variations": []},
    {"name": "Супермен", "muscle_group": "спина/поясница", "difficulty": 1,
     "technique": "Лёжа на животе одновременно поднимай руки и ноги, шея нейтральна.",
     "variations": []},
    # Плечи / лопатки / ротаторы
    {"name": "Лопаточная ретракция у стены", "muscle_group": "плечи/лопатки", "difficulty": 1,
     "technique": "Сводя лопатки, прижимай и опускай их; движение короткое и контролируемое.",
     "variations": []},
    {"name": "Wall slides", "muscle_group": "плечи/лопатки", "difficulty": 2,
     "technique": "Спина и руки у стены, скользи руками вверх-вниз в короткой безболезненной амплитуде.",
     "variations": []},
    {"name": "Изометрия наружной ротации", "muscle_group": "плечи/ротаторы", "difficulty": 1,
     "technique": "Локоть прижат к боку, дави наружу в неподвижную опору, удерживай 10–20 с.",
     "variations": []},
    {"name": "Y-T-W у стены", "muscle_group": "плечи/спина", "difficulty": 2,
     "technique": "У стены рисуй руками буквы Y, T, W, сводя лопатки, микроподъём.",
     "variations": []},
    # Спина (тяги)
    {"name": "Австралийские подтягивания", "muscle_group": "спина/бицепс", "difficulty": 3,
     "technique": "Под низкой опорой тяни грудь к перекладине, тело прямое, лопатки сводишь.",
     "variations": []},
    {"name": "Подтягивания", "muscle_group": "спина/бицепс", "difficulty": 4,
     "technique": "Из виса тяни себя вверх до подбородка над перекладиной, без раскачки.",
     "variations": ["с резинкой", "негативные"]},
]

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


async def seed_exercises(db: AsyncSession) -> None:
    """Идемпотентно добавляет отсутствующие упражнения (по названию)."""
    res = await db.execute(select(Exercise.name))
    existing = {name for name in res.scalars().all()}
    added = False
    for data in EXERCISES:
        if data["name"] not in existing:
            db.add(Exercise(**data))
            added = True
    if added:
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
