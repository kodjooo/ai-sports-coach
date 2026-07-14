"""Конфигурация приложения из переменных окружения."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telegram
    tg_token: str

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-5"
    openai_embed_model: str = "text-embedding-3-small"
    # Модель распознавания речи (голосовые сообщения)
    openai_transcribe_model: str = "whisper-1"
    # Режим рассуждений для reasoning-моделей (gpt-5): minimal|low|medium|high
    openai_reasoning_effort: str = "low"
    # Более качественный режим для онбординга (генерация персонального промпта)
    openai_reasoning_effort_onboarding: str = "medium"

    # PostgreSQL
    postgres_user: str = "coach"
    postgres_password: str = "coach"
    postgres_db: str = "coach"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # ChromaDB
    chroma_host: str = "chroma"
    chroma_port: int = 8000

    # Redis (хранилище FSM — состояние переживает перезапуск)
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # Планировщик
    tz: str = "Europe/Chisinau"
    reminder_hour: int = 8
    reminder_minute: int = 0

    # Логирование переписки (для анализа). Выключено по умолчанию.
    log_dialog: bool = False
    # Список tg_id через запятую — логировать только их. Пусто = все (при log_dialog=true).
    log_dialog_users: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        # Async-драйвер asyncpg для SQLAlchemy
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def log_dialog_user_ids(self) -> set[int]:
        ids: set[int] = set()
        for part in self.log_dialog_users.split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return ids

    @property
    def sync_database_url(self) -> str:
        # Синхронный URL для Alembic
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
