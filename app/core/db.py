"""Async-подключение к PostgreSQL через SQLAlchemy."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)

# Фабрика сессий; expire_on_commit=False, чтобы объекты жили после commit
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
