"""FSM-состояния бота."""
from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    """Регистрация нового пользователя через LLM-интервью."""

    interview = State()       # свободный диалог-интервью с уточнениями
    environment = State()     # где тренируется (дом/улица/зал/микс)
    equipment = State()       # что есть из инвентаря (текст)
    schedule = State()        # выбор частоты/дней/времени кнопками
    custom_time = State()     # ручной ввод времени тренировки
    waiting_weight = State()  # вопрос про вес числом (если не сказан в интервью)
    waiting_height = State()  # вопрос про рост (если не сказан в интервью)
    sex = State()             # пол (кнопки)
    waiting_age = State()     # возраст числом
    activity = State()        # уровень активности (кнопки)
    level = State()           # уровень подготовки (кнопки)


class Workout(StatesGroup):
    """Активная тренировка."""

    in_progress = State()   # ждём выбор повторов/ощущения
    manual_reps = State()   # ручной ввод числа повторов/секунд


class Nutrition(StatesGroup):
    """Учёт питания."""

    confirming = State()   # показан разбор блюда, ждём Сохранить/Исправить
    correcting = State()   # ждём текстовую правку разбора
