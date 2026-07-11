# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копируем код приложения и конфигурацию миграций
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

# Запуск: применяем миграции, засеваем справочники и стартуем бота
CMD ["python", "-m", "app.main"]
