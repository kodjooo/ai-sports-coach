"""Общая настройка тестов: подставляем обязательные переменные окружения."""
import os

os.environ.setdefault("TG_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("CHROMA_HOST", "localhost")
