"""Обёртка над ChromaDB — семантическая память тренера.

Храним одну коллекцию, фильтруем по user_id в metadata.
Эмбеддинги считаем сами через OpenAI (text-embedding-3-small).
"""
from __future__ import annotations

import logging

import chromadb

from app.config import settings
from app.core import llm

logger = logging.getLogger(__name__)

COLLECTION_NAME = "coach_memory"

_client: chromadb.api.ClientAPI | None = None


def _get_collection():
    global _client
    if _client is None:
        _client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    # embedding_function=None — передаём эмбеддинги вручную
    return _client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=None)


async def add_memory(user_id: int, doc_id: str, text: str, metadata: dict) -> None:
    """Кладёт документ в память с эмбеддингом OpenAI."""
    try:
        vector = await llm.embed(text)
        meta = {"user_id": user_id, **metadata}
        _get_collection().add(ids=[doc_id], documents=[text], embeddings=[vector], metadatas=[meta])
    except Exception as exc:  # память не критична для основного сценария
        logger.warning("Не удалось записать в ChromaDB: %s", exc)


async def query_memory(user_id: int, query_text: str, n_results: int = 6) -> list[str]:
    """Возвращает top-K релевантных фрагментов памяти пользователя."""
    try:
        vector = await llm.embed(query_text)
        res = _get_collection().query(
            query_embeddings=[vector],
            n_results=n_results,
            where={"user_id": user_id},
        )
        docs = res.get("documents") or [[]]
        return docs[0]
    except Exception as exc:
        logger.warning("Не удалось прочитать из ChromaDB: %s", exc)
        return []
