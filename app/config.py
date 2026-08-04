"""Конфигурация приложения из переменных окружения."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telegram
    tg_token: str

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-5"
    # Модель генерации плана: gpt-5.6-luna — качество ≈ gpt-5, но в ~3× дешевле и ×5 быстрее
    openai_model_plan: str = "gpt-5.6-luna"
    # Модель распознавания еды по фото: gpt-5. Тест на 14 фото: gpt-5 и gpt-5.1 одинаково точны
    # на весах/этикетках (обе читают идеально), но gpt-5.1 систематически ЗАНИЖАЕТ граммы
    # объёмной еды без весов (суши 840 vs 1134, банан 150 vs 180) — опасно для дефицита калорий.
    # Цена одинаковая → держим gpt-5 (реалистичнее оценивает объём, не занижает).
    openai_model_food: str = "gpt-5"
    # Модель для одиночной текстовой генерации без инструментов (фидбек после тренировки,
    # недельный вывод): luna — качество ≈ gpt-5 на связном тексте, но дешевле/быстрее.
    # ВАЖНО: только там, где НЕ нужны function tools (иначе luna требует reasoning=none и не вызывает их).
    openai_model_text: str = "gpt-5.6-luna"
    # Компактный режим тренировки: удалять предыдущие шаги, оставляя одну активную карточку
    workout_compact: bool = True
    # Экономная модель для узких/служебных задач (в ~10 раз дешевле)
    openai_model_mini: str = "gpt-5-mini"
    openai_embed_model: str = "text-embedding-3-small"
    # Модель распознавания речи (голосовые сообщения)
    openai_transcribe_model: str = "whisper-1"
    # Режим рассуждений для reasoning-моделей (gpt-5): minimal|low|medium|high
    openai_reasoning_effort: str = "low"
    # Режим для онбординга (low экономит reasoning-токены при том же качестве)
    openai_reasoning_effort_onboarding: str = "low"
    # Режим для генерации плана: low. Надёжность формата (все дни, ровно per_day) держит код
    # (_sanitize_plan), а не reasoning — прямое сравнение low vs medium показало, что medium
    # выигрыша по балансу не даёт, но стоит дороже/медленнее. Держим low ради экономии.
    openai_reasoning_effort_plan: str = "low"

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

    # USDA FoodData Central — точная база для генерик-продуктов.
    # Бесплатный ключ: https://fdc.nal.usda.gov/api-key-signup.html (для теста — DEMO_KEY)
    usda_api_key: str = ""

    # Каталог GIF-анимаций упражнений (на Docker volume, генерируется scripts/build_exercise_gifs.py)
    exercise_gif_dir: str = "/app/media/exercises"

    # Планировщик
    tz: str = "Europe/Chisinau"
    reminder_hour: int = 8
    reminder_minute: int = 0

    # Логирование переписки (для анализа). Выключено по умолчанию.
    log_dialog: bool = False
    # Список tg_id через запятую — логировать только их. Пусто = все (при log_dialog=true).
    log_dialog_users: str = ""

    # Админы (tg_id через запятую) — без каких-либо лимитов и предохранителя.
    admin_tg_ids: str = ""

    # Глобальный предохранитель по стоимости LLM за день (в $). Софт — деградация/алерт,
    # хард — временно отключаем дорогие LLM-функции (кнопочный функционал продолжает работать).
    daily_cost_soft_usd: float = 5.0
    daily_cost_hard_usd: float = 10.0

    # Лимиты дорогих действий. trial — суммарный запас для новичка (до «активации» = прошёл
    # онбординг); daily — суточный лимит для активированного пользователя.
    limit_food_trial: int = 10
    limit_food_daily: int = 15
    limit_chat_trial: int = 15
    limit_chat_daily: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def admin_ids(self) -> set[int]:
        ids: set[int] = set()
        for part in self.admin_tg_ids.split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return ids

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
