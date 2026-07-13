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
    goal: Mapped[str | None] = mapped_column(String)  # напр. 'похудеть+сила'
    # Персональная настройка тренера по итогам интервью
    system_prompt: Mapped[str | None] = mapped_column(String)  # сгенерированный системный промпт
    profile_summary: Mapped[str | None] = mapped_column(String)  # краткая выжимка о клиенте
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)  # 'Отжимания от пола'
    muscle_group: Mapped[str | None] = mapped_column(String)  # 'грудь/трицепс'
    difficulty: Mapped[int | None] = mapped_column(Integer)  # 1..5
    technique: Mapped[str | None] = mapped_column(String)  # описание техники
    variations: Mapped[list | None] = mapped_column(JSONB)  # ['от стены', ...]


class WorkoutTemplate(Base):
    __tablename__ = "workout_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    label: Mapped[str | None] = mapped_column(String)  # 'День A'
    weekday: Mapped[int | None] = mapped_column(Integer)  # 0..6
    active: Mapped[bool] = mapped_column(Boolean, default=True)

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


class Meal(Base):
    """Фаза 2/3 — учёт питания."""

    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    photo_file_id: Mapped[str | None] = mapped_column(String)
    grams: Mapped[Decimal | None] = mapped_column(Numeric)
    kcal_est: Mapped[Decimal | None] = mapped_column(Numeric)
    note: Mapped[str | None] = mapped_column(String)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
