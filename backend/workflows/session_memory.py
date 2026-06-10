from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol

from app.db import postgres_db

logger = logging.getLogger(__name__)


class SessionMemoryProvider(Protocol):
    def get_messages(self, thread_id: str) -> list[dict[str, Any]]: ...

    def append_message(self, thread_id: str, role: str, content: str) -> None: ...

    def summarize_context(self, thread_id: str, max_messages: int = 8) -> str: ...


class PostgresSessionMemoryStore:
    def __init__(self, _storage_dir: Path | None = None) -> None:
        postgres_db.ensure_schema()
        self._pool = postgres_db.get_pool()

    def get_messages(self, thread_id: str) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT role, content
                    FROM conversation_messages
                    WHERE thread_id = %s
                    ORDER BY id ASC
                    """,
                    (thread_id,),
                )
                rows = cur.fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def append_message(self, thread_id: str, role: str, content: str) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO workflow_runs (
                        thread_id, status, input, input_summary,
                        created_at, updated_at, started_at
                    ) VALUES (%s, %s, %s, %s, NOW(), NOW(), NOW())
                    ON CONFLICT (thread_id) DO NOTHING
                    """,
                    (
                        thread_id,
                        "running",
                        content,
                        self._summarize_input(content),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO conversation_messages (thread_id, role, content)
                    VALUES (%s, %s, %s)
                    """,
                    (thread_id, role, content),
                )

    @staticmethod
    def _summarize_input(input_text: str, max_len: int = 96) -> str:
        normalized = " ".join(input_text.split())
        if len(normalized) <= max_len:
            return normalized
        return f"{normalized[: max_len - 3]}..."

    def summarize_context(self, thread_id: str, max_messages: int = 8) -> str:
        messages = self.get_messages(thread_id)
        if not messages:
            return ""
        window = messages[-max_messages:]
        lines = [f"{item['role']}: {item['content']}" for item in window]
        return "\n".join(lines)


class FoundrySessionMemoryStore:
    """Placeholder Foundry memory provider until remote persistence is integrated."""

    def __init__(self, _storage_dir: Path | None = None) -> None:
        self._messages: dict[str, list[dict[str, Any]]] = {}

    def get_messages(self, thread_id: str) -> list[dict[str, Any]]:
        return [dict(message) for message in self._messages.get(thread_id, [])]

    def append_message(self, thread_id: str, role: str, content: str) -> None:
        self._messages.setdefault(thread_id, []).append({"role": role, "content": content})

    def summarize_context(self, thread_id: str, max_messages: int = 8) -> str:
        messages = self.get_messages(thread_id)
        if not messages:
            return ""
        window = messages[-max_messages:]
        lines = [f"{item['role']}: {item['content']}" for item in window]
        return "\n".join(lines)


def create_memory_store(provider: str, storage_dir: Path | None = None) -> SessionMemoryProvider:
    if provider == "postgres":
        return PostgresSessionMemoryStore(storage_dir)
    if provider == "foundry_memory":
        logger.warning(
            "MEMORY_PROVIDER=foundry_memory is an in-process placeholder and is not durable across process restarts."
        )
        return FoundrySessionMemoryStore(storage_dir)
    raise ValueError(f"Unsupported MEMORY_PROVIDER: {provider}")


# Backward compatible alias for existing imports/tests.
SessionMemoryStore = PostgresSessionMemoryStore
