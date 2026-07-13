"""FSM-состояния бота."""
from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    """Регистрация нового пользователя через LLM-интервью."""

    interview = State()       # свободный диалог-интервью с уточнениями
    schedule = State()        # выбор частоты/дней/времени кнопками
    custom_time = State()     # ручной ввод времени тренировки
    waiting_weight = State()  # обязательный вопрос про вес числом


class Workout(StatesGroup):
    """Активная тренировка."""

    in_progress = State()  # ждём выбор повторов/ощущения


class Nutrition(StatesGroup):
    """Учёт питания (Фаза 3)."""

    waiting_grams = State()  # ждём вес порции после фото
