# Виртуальный тренер — Telegram-бот

Персональный фитнес-тренер в Telegram: ведёт по плану тренировок, логирует
подходы кнопками, помнит историю (векторная память) и даёт советы через GPT-4.

Запуск и разработка — **только через Docker Desktop**, без локального окружения.

## Стек

- Python 3.12, aiogram 3.x (long polling)
- PostgreSQL (структурированные данные) + Alembic (миграции)
- ChromaDB (семантическая память)
- OpenAI GPT-5 (диалог, фидбек, Vision) + эмбеддинги `text-embedding-3-small`
- Распознавание голосовых сообщений (`whisper-1`)
- Учёт КБЖУ по фото/тексту; уточнение по USDA FoodData Central + OpenFoodFacts
- Персональный онбординг: LLM-интервью → индивидуальный системный промпт тренера
- APScheduler (утренние напоминания, недельный отчёт)

## Сервисы docker-compose

- `postgres` — база данных (volume `pg_data`).
- `chroma` — векторная БД (volume `chroma_data`).
- `redis` — хранилище состояния диалога (FSM), переживает перезапуск (volume `redis_data`).
- `bot` — приложение: применяет миграции, засевает справочник упражнений и запускает бота.
- `tests` — прогон pytest (профиль `test`, в обычном запуске не поднимается).

## Настройка

1. Скопировать шаблон окружения и заполнить значения:
   ```bash
   cp .env.example .env
   ```
   Обязательно указать:
   - `TG_TOKEN` — токен бота от @BotFather.
   - `OPENAI_API_KEY` — ключ с https://platform.openai.com/api-keys
   - `POSTGRES_PASSWORD` — надёжный пароль БД.

## Запуск

```bash
docker compose up -d --build
```

Бот стартует в режиме long polling. Логи:

```bash
docker compose logs -f bot
```

Остановка:

```bash
docker compose down          # с сохранением данных (volumes остаются)
docker compose down -v       # удалить и данные
```

## Тесты

```bash
docker compose --profile test run --rm tests
```

## Логирование переписки (для анализа)

По умолчанию выключено. Включить в `.env`:

```
LOG_DIALOG=true
LOG_DIALOG_USERS=            # пусто = все; или список tg_id через запятую
```

Просмотр: `docker compose logs bot | grep DIALOG`.

## Миграции БД

Миграции применяются автоматически при старте контейнера `bot` (`alembic upgrade head`).
Создать новую миграцию после изменения моделей:

```bash
docker compose run --rm bot alembic revision -m "описание"
```

## Развёртывание на VPS (Linux)

1. Установить Docker и Docker Compose plugin.
2. Склонировать репозиторий:
   ```bash
   git clone https://github.com/kodjooo/ai-sports-coach.git
   cd ai-sports-coach
   ```
3. Создать `.env` (см. раздел «Настройка»).
4. Запустить: `docker compose up -d --build`.
5. Данные хранятся в volumes `pg_data` и `chroma_data`.

**Бэкап PostgreSQL** (пример, по cron):

```bash
docker compose exec -T postgres pg_dump -U coach coach > backup_$(date +%F).sql
```

## Структура

```
app/
  main.py            — точка входа (миграции, сид, планировщик, polling)
  config.py          — настройки из .env
  keyboards.py       — inline/reply клавиатуры
  states.py          — FSM
  handlers/          — start (интервью), menu, workout, chat, voice, nutrition
  core/              — db, models, repository, llm, vector, context, progress, seed
  scheduler/         — reminders (APScheduler)
migrations/          — Alembic
tests/               — pytest
```
