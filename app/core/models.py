"""ORM-модели по схеме из docs/requirements.md (раздел 4)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric)
    height_cm: Mapped[int | None] = mapped_column(Integer)  # рост, см
    sex: Mapped[str | None] = mapped_column(String)  # 'м' | 'ж'
    age: Mapped[int | None] = mapped_column(Integer)
    activity: Mapped[str | None] = mapped_column(String)  # уровень активности (ключ)
    goal: Mapped[str | None] = mapped_column(String)  # напр. 'похудеть+сила'
    # Персональная настройка тренера по итогам интервью
    system_prompt: Mapped[str | None] = mapped_column(String)  # сгенерированный системный промпт
    profile_summary: Mapped[str | None] = mapped_column(String)  # краткая выжимка о клиенте
    # Время тренировки для напоминаний (часы:минуты)
    train_hour: Mapped[int | None] = mapped_column(Integer)
    train_minute: Mapped[int | None] = mapped_column(Integer)
    # Бегущее резюме старой переписки с тренером (авто-суммаризация)
    chat_summary: Mapped[str | None] = mapped_column(String)
    # Где тренируется и что есть из инвентаря
    environment: Mapped[str | None] = mapped_column(String)  # дом/улица/зал/микс
    equipment: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)  # 'Отжимания от пола'
    muscle_group: Mapped[str | None] = mapped_column(String)  # 'грудь/трицепс'
    difficulty: Mapped[int | None] = mapped_column(Integer)  # 1..5
    technique: Mapped[str | None] = mapped_column(String)  # описание техники
    variations: Mapped[list | None] = mapped_column(JSONB)  # ['от стены', ...]
    environment: Mapped[str | None] = mapped_column(String)  # дом/улица/зал
    equipment: Mapped[str | None] = mapped_column(String)    # инвентарь


class WorkoutTemplate(Base):
    __tablename__ = "workout_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    label: Mapped[str | None] = mapped_column(String)  # 'День A'
    weekday: Mapped[int | None] = mapped_column(Integer)  # 0..6
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    warmup: Mapped[str | None] = mapped_column(String)   # разминка дня
    cooldown: Mapped[str | None] = mapped_column(String)  # заминка дня

    items: Mapped[list["TemplateItem"]] = relationship(
        back_populates="template", order_by="TemplateItem.order_idx"
    )


class TemplateItem(Base):
    __tablename__ = "template_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    template_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workout_templates.id"))
    exercise_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("exercises.id"))
    target_sets: Mapped[int | None] = mapped_column(Integer)
    target_reps: Mapped[int | None] = mapped_column(Integer)
    rest_sec: Mapped[int | None] = mapped_column(Integer)  # отдых между подходами, сек
    order_idx: Mapped[int | None] = mapped_column(Integer)

    template: Mapped[WorkoutTemplate] = relationship(back_populates="items")
    exercise: Mapped[Exercise] = relationship()


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    template_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("workout_templates.id"))
    planned_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String)  # planned/done/skipped/moved
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SetLog(Base):
    __tablename__ = "set_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sessions.id"))
    exercise_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("exercises.id"))
    set_idx: Mapped[int | None] = mapped_column(Integer)
    reps: Mapped[int | None] = mapped_column(Integer)
    effort: Mapped[str | None] = mapped_column(String)  # easy/ok/hard
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WeightLog(Base):
    __tablename__ = "weight_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    """Окно переписки пользователя с тренером (короткая память диалога)."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String)  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Meal(Base):
    """Приём пищи (итоговые БЖУ/ккал)."""

    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    photo_file_id: Mapped[str | None] = mapped_column(String)
    grams: Mapped[Decimal | None] = mapped_column(Numeric)      # устар., не используется
    kcal_est: Mapped[Decimal | None] = mapped_column(Numeric)   # устар., не используется
    kcal: Mapped[Decimal | None] = mapped_column(Numeric)
    protein: Mapped[Decimal | None] = mapped_column(Numeric)
    fat: Mapped[Decimal | None] = mapped_column(Numeric)
    carbs: Mapped[Decimal | None] = mapped_column(Numeric)
    note: Mapped[str | None] = mapped_column(String)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MealItem(Base):
    """Ингредиент приёма пищи."""

    __tablename__ = "meal_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    meal_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("meals.id"))
    name: Mapped[str] = mapped_column(String)
    grams: Mapped[Decimal | None] = mapped_column(Numeric)
    kcal: Mapped[Decimal | None] = mapped_column(Numeric)
    protein: Mapped[Decimal | None] = mapped_column(Numeric)
    fat: Mapped[Decimal | None] = mapped_column(Numeric)
    carbs: Mapped[Decimal | None] = mapped_column(Numeric)
