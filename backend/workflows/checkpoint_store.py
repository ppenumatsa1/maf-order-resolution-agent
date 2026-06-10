from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db import postgres_db


class CheckpointStore:
    def __init__(self, _storage_dir: Path | None = None) -> None:
        postgres_db.ensure_schema()
        self._pool = postgres_db.get_pool()

    def create(self, thread_id: str, state: dict[str, Any]) -> dict[str, Any]:
        checkpoint = {
            "checkpoint_id": str(uuid4()),
            "thread_id": thread_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending_hitl",
            "state": state,
        }
        self._save(checkpoint)
        return checkpoint

    def get(self, checkpoint_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT checkpoint_id, thread_id, created_at, status, state, reviewer, comments
                    FROM checkpoints
                    WHERE checkpoint_id = %s::uuid
                    """,
                    (checkpoint_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "checkpoint_id": str(row["checkpoint_id"]),
                    "thread_id": row["thread_id"],
                    "created_at": row["created_at"].astimezone(timezone.utc).isoformat(),
                    "status": row["status"],
                    "state": row["state"] or {},
                    "reviewer": row["reviewer"],
                    "comments": row["comments"],
                }

    def update(self, checkpoint: dict[str, Any]) -> None:
        self._save(checkpoint)

    def try_resolve(
        self,
        *,
        checkpoint_id: str,
        resolved_status: str,
        reviewer: str,
        comments: str | None,
    ) -> bool:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE checkpoints
                    SET status = %s,
                        reviewer = %s,
                        comments = %s,
                        updated_at = NOW()
                    WHERE checkpoint_id = %s::uuid
                      AND status IN ('pending_hitl', 'pending')
                    """,
                    (resolved_status, reviewer, comments, checkpoint_id),
                )
                return cur.rowcount == 1

    def _save(self, checkpoint: dict[str, Any]) -> None:
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
                        checkpoint["thread_id"],
                        "running",
                        "checkpoint-created",
                        "checkpoint-created",
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO checkpoints (
                        checkpoint_id, thread_id, created_at, status, state,
                        reviewer, comments, updated_at
                    ) VALUES (
                        %s::uuid, %s, %s, %s, %s::jsonb,
                        %s, %s, NOW()
                    )
                    ON CONFLICT (checkpoint_id)
                    DO UPDATE SET
                        status = EXCLUDED.status,
                        state = EXCLUDED.state,
                        reviewer = EXCLUDED.reviewer,
                        comments = EXCLUDED.comments,
                        updated_at = NOW()
                    """,
                    (
                        checkpoint["checkpoint_id"],
                        checkpoint["thread_id"],
                        checkpoint["created_at"],
                        checkpoint["status"],
                        self._json_dumps(checkpoint.get("state", {})),
                        checkpoint.get("reviewer"),
                        checkpoint.get("comments"),
                    ),
                )

    @staticmethod
    def _json_dumps(value: dict[str, Any]) -> str:
        import json

        return json.dumps(value)
