"""Тесты избранных блюд (sqlite in-memory): дедуп по названию, порядок по частоте, владелец."""
import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core import repository as repo
from app.core.models import Base, FavoriteMeal, Meal, MealItem, User


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        tables = [t.__table__ for t in (User, Meal, MealItem, FavoriteMeal)]
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    return async_sessionmaker(engine, expire_on_commit=False)


def _run(coro):
    return asyncio.run(coro)


def test_add_from_meal_and_dedupe():
    async def scenario():
        Sm = await _make_session()
        async with Sm() as db:
            db.add(User(id=1, tg_id=1, name="A"))
            db.add(Meal(id=5, user_id=1, kcal=25, note="Американо с сахаром",
                        logged_at=datetime.now(timezone.utc)))
            db.add(MealItem(id=50, meal_id=5, name="Кофе", grams=250, kcal=5))
            db.add(MealItem(id=51, meal_id=5, name="Сахар", grams=6, kcal=20))
            await db.commit()

            fav = await repo.add_favorite_from_meal(db, 1, 5)
            assert fav is not None and fav.dish == "Американо с сахаром"
            payload = json.loads(fav.payload)
            assert payload["total"]["kcal"] == 25
            assert len(payload["items"]) == 2

            # повторное добавление того же блюда — не плодит дубликат
            again = await repo.add_favorite_from_meal(db, 1, 5)
            favs = await repo.list_favorites(db, 1)
            assert len(favs) == 1
            assert again.id == fav.id
    _run(scenario())


def test_list_order_by_usage():
    async def scenario():
        Sm = await _make_session()
        async with Sm() as db:
            db.add(User(id=1, tg_id=1, name="A"))
            db.add(FavoriteMeal(id=1, user_id=1, dish="Редкое", kcal=100, payload="{}", times_used=0))
            db.add(FavoriteMeal(id=2, user_id=1, dish="Частое", kcal=200, payload="{}", times_used=5))
            await db.commit()
            favs = await repo.list_favorites(db, 1)
            assert [f.dish for f in favs] == ["Частое", "Редкое"]  # частое сверху
            await repo.bump_favorite(db, 1)
            await repo.bump_favorite(db, 1)  # +2 → всё ещё меньше 5
            assert (await repo.get_favorite(db, 1, 1)).times_used == 2
    _run(scenario())


def test_delete_ownership():
    async def scenario():
        Sm = await _make_session()
        async with Sm() as db:
            db.add(User(id=1, tg_id=1, name="A"))
            db.add(User(id=2, tg_id=2, name="B"))
            db.add(FavoriteMeal(id=7, user_id=1, dish="X", kcal=1, payload="{}", times_used=0))
            await db.commit()
            assert await repo.delete_favorite(db, 7, 2) is False  # чужое
            assert await repo.delete_favorite(db, 7, 1) is True
            assert await repo.get_favorite(db, 7, 1) is None
    _run(scenario())
