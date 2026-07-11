"""FSM-состояния бота."""
from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    """Регистрация нового пользователя."""

    waiting_goal = State()
    waiting_weight = State()


class Workout(StatesGroup):
    """Активная тренировка."""

    in_progress = State()  # ждём выбор повторов/ощущения


class Nutrition(StatesGroup):
    """Учёт питания (Фаза 3)."""

    waiting_grams = State()  # ждём вес порции после фото
