"""Тесты статистики репозитория на sqlite in-memory:
- тренировкой считается только done-сессия с ≥1 подходом (пустые не в счёт),
- рекорды не учитывают повторы = 0,
- delete_meal не удаляет чужой приём пищи.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core import repository as repo
from app.core.models import Base, Meal, Session, SetLog, User


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        # создаём только нужные таблицы (у exercises — JSONB, sqlite его не соберёт)
        tables = [t.__table__ for t in (User, Session, SetLog, Meal)]
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    return async_sessionmaker(engine, expire_on_commit=False)


def _run(coro):
    return asyncio.run(coro)


def test_empty_session_not_counted(monkeypatch):
    async def scenario():
        Sm = await _make_session()
        async with Sm() as db:
            db.add(User(id=1, tg_id=1, name="T"))
            today = date(2026, 7, 25)
            # done с подходами (реальная тренировка)
            db.add(Session(id=10, user_id=1, planned_date=today, status="done"))
            db.add(SetLog(id=100, session_id=10, exercise_id=1, reps=10))
            # done БЕЗ подходов (пустая — только разминка/заминка)
            db.add(Session(id=11, user_id=1, planned_date=today, status="done"))
            # planned (не тренировка)
            db.add(Session(id=12, user_id=1, planned_date=today, status="planned"))
            await db.commit()

            total = await repo.total_done_sessions(db, 1)
            week = await repo.count_workouts_in_period(db, 1, today - timedelta(days=7))
            assert total == 1  # пустая done-сессия не считается
            assert week == 1
    _run(scenario())


def test_records_exclude_zero_reps(monkeypatch):
    async def stub_get_exercise(db, ex_id):
        return type("E", (), {"name": f"Упр{ex_id}"})()
    monkeypatch.setattr(repo, "get_exercise", stub_get_exercise)

    async def scenario():
        Sm = await _make_session()
        async with Sm() as db:
            db.add(User(id=1, tg_id=1, name="T"))
            db.add(Session(id=10, user_id=1, planned_date=date(2026, 7, 25), status="done"))
            db.add(SetLog(id=100, session_id=10, exercise_id=1, reps=12))
            db.add(SetLog(id=101, session_id=10, exercise_id=1, reps=0))   # 0 — не рекорд
            db.add(SetLog(id=102, session_id=10, exercise_id=2, reps=0))   # только 0 → без рекорда
            await db.commit()

            recs = dict(await repo.exercise_records(db, 1))
            assert recs.get("Упр1") == 12      # максимум без учёта 0
            assert "Упр2" not in recs          # упражнение только с 0 повторов не попадает
    _run(scenario())


def test_delete_meal_ownership():
    async def scenario():
        Sm = await _make_session()
        async with Sm() as db:
            db.add(User(id=1, tg_id=1, name="A"))
            db.add(User(id=2, tg_id=2, name="B"))
            db.add(Meal(id=5, user_id=1, kcal=300, logged_at=datetime.now(timezone.utc)))
            await db.commit()

            assert await repo.delete_meal(db, 5, 2) is False  # чужой — не удаляем
            assert await repo.delete_meal(db, 5, 1) is True   # владелец — удаляем
            assert await repo.delete_meal(db, 5, 1) is False  # уже удалён
    _run(scenario())
