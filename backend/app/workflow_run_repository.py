from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.db import postgres_db
from app.models import (
    PendingApproval,
    WorkflowEvent,
    WorkflowRunDetailsResponse,
    WorkflowRunListItem,
    WorkflowRunMetadata,
    WorkflowRunStatus,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _duration_ms(started_at: str | None, completed_at: str | None) -> int | None:
    if not started_at or not completed_at:
        return None
    try:
        started = datetime.fromisoformat(started_at)
        completed = datetime.fromisoformat(completed_at)
    except ValueError:
        return None
    return max(0, int((completed - started).total_seconds() * 1000))


class WorkflowRunRepository:
    def __init__(self) -> None:
        postgres_db.ensure_schema()
        self._pool = postgres_db.get_pool()

    def create_workflow_run(self, thread_id: str, input_text: str) -> dict[str, Any]:
        now = _utc_now_iso()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO workflow_runs (
                        thread_id, status, input, input_summary,
                        created_at, updated_at, started_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (thread_id) DO NOTHING
                    """,
                    (
                        thread_id,
                        "running",
                        input_text,
                        self._summarize_input(input_text),
                        now,
                        now,
                        now,
                    ),
                )
                cur.execute(
                    """
                    SELECT thread_id, status, input, input_summary,
                           created_at, updated_at
                    FROM workflow_runs
                    WHERE thread_id = %s
                    """,
                    (thread_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError(f"Failed to create workflow run: {thread_id}")
                return {
                    "thread_id": row["thread_id"],
                    "status": row["status"],
                    "input": row["input"],
                    "input_summary": row["input_summary"],
                    "created_at": _as_iso(row["created_at"]),
                    "updated_at": _as_iso(row["updated_at"]),
                }

    def list_workflow_runs(
        self,
        page: int,
        page_size: int,
        status: WorkflowRunStatus | None = None,
    ) -> tuple[list[WorkflowRunListItem], int]:
        offset = (page - 1) * page_size
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute(
                        "SELECT COUNT(*) AS total FROM workflow_runs WHERE status = %s",
                        (status,),
                    )
                    total = int(cur.fetchone()["total"])
                    cur.execute(
                        """
                        SELECT thread_id, status, input_summary, created_at, updated_at
                        FROM workflow_runs
                        WHERE status = %s
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (status, page_size, offset),
                    )
                else:
                    cur.execute("SELECT COUNT(*) AS total FROM workflow_runs")
                    total = int(cur.fetchone()["total"])
                    cur.execute(
                        """
                        SELECT thread_id, status, input_summary, created_at, updated_at
                        FROM workflow_runs
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (page_size, offset),
                    )

                rows = cur.fetchall()

        items = [
            WorkflowRunListItem(
                thread_id=row["thread_id"],
                status=row["status"],
                input_summary=row["input_summary"],
                created_at=_as_iso(row["created_at"]) or _utc_now_iso(),
                updated_at=_as_iso(row["updated_at"]) or _utc_now_iso(),
            )
            for row in rows
        ]
        return items, total

    def get_workflow_run(self, thread_id: str) -> WorkflowRunDetailsResponse | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT thread_id, status, input, latest_output,
                           started_at, completed_at, duration_ms, current_stage
                    FROM workflow_runs
                    WHERE thread_id = %s
                    """,
                    (thread_id,),
                )
                run = cur.fetchone()
                if not run:
                    return None

                cur.execute(
                    """
                    SELECT id, type, thread_id, timestamp, payload
                    FROM workflow_events
                    WHERE thread_id = %s
                    ORDER BY timestamp ASC, id ASC
                    """,
                    (thread_id,),
                )
                event_rows = cur.fetchall()

                cur.execute(
                    """
                    SELECT approval_id, checkpoint_id, action, order_id, amount,
                           question, reviewer, comments, status, requested_at, resolved_at
                    FROM approvals
                    WHERE thread_id = %s
                    ORDER BY requested_at DESC
                    """,
                    (thread_id,),
                )
                approval_rows = cur.fetchall()

        events = [
            WorkflowEvent(
                id=str(row["id"]),
                type=row["type"],
                thread_id=row["thread_id"],
                timestamp=_as_iso(row["timestamp"]) or _utc_now_iso(),
                payload=row["payload"] or {},
            )
            for row in event_rows
        ]
        approvals = [
            PendingApproval(
                approval_id=str(row["approval_id"]),
                checkpoint_id=str(row["checkpoint_id"]),
                action=row["action"],
                order_id=row["order_id"],
                amount=row["amount"],
                question=row["question"],
                reviewer=row["reviewer"],
                comments=row["comments"],
                status=row["status"],
                requested_at=_as_iso(row["requested_at"]) or _utc_now_iso(),
                resolved_at=_as_iso(row["resolved_at"]),
            )
            for row in approval_rows
        ]

        metadata = WorkflowRunMetadata(
            thread_id=run["thread_id"],
            status=run["status"],
            started_at=_as_iso(run["started_at"]),
            completed_at=_as_iso(run["completed_at"]),
            duration_ms=run["duration_ms"],
            current_stage=run["current_stage"],
        )

        return WorkflowRunDetailsResponse(
            thread_id=run["thread_id"],
            status=run["status"],
            input=run["input"],
            events=events,
            pending_approvals=approvals,
            latest_output=run["latest_output"],
            metadata=metadata,
        )

    def append_workflow_event(self, thread_id: str, event: WorkflowEvent) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO workflow_events (id, thread_id, type, timestamp, payload)
                    VALUES (%s::uuid, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        event.id,
                        thread_id,
                        event.type,
                        event.timestamp,
                        self._json_dumps(event.payload),
                    ),
                )
                cur.execute(
                    "UPDATE workflow_runs SET updated_at = %s WHERE thread_id = %s",
                    (_utc_now_iso(), thread_id),
                )

    def update_workflow_status(self, thread_id: str, status: WorkflowRunStatus) -> None:
        now = _utc_now_iso()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET status = %s,
                        updated_at = %s
                    WHERE thread_id = %s
                    """,
                    (status, now, thread_id),
                )
                if status in {"completed", "failed", "escalated"}:
                    cur.execute(
                        """
                        UPDATE workflow_runs
                        SET completed_at = COALESCE(completed_at, %s)
                        WHERE thread_id = %s
                        """,
                        (now, thread_id),
                    )
                    cur.execute(
                        """
                        SELECT started_at, completed_at
                        FROM workflow_runs
                        WHERE thread_id = %s
                        """,
                        (thread_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        duration = _duration_ms(
                            _as_iso(row["started_at"]),
                            _as_iso(row["completed_at"]),
                        )
                        cur.execute(
                            """
                            UPDATE workflow_runs
                            SET duration_ms = %s
                            WHERE thread_id = %s
                            """,
                            (duration, thread_id),
                        )

    def update_current_stage(self, thread_id: str, stage: str | None) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET current_stage = %s,
                        updated_at = %s
                    WHERE thread_id = %s
                    """,
                    (stage, _utc_now_iso(), thread_id),
                )

    def update_latest_output(self, thread_id: str, output: dict[str, Any]) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET latest_output = %s::jsonb,
                        updated_at = %s
                    WHERE thread_id = %s
                    """,
                    (self._json_dumps(output), _utc_now_iso(), thread_id),
                )

    def add_pending_approval(self, thread_id: str, approval: dict[str, Any]) -> None:
        now = _utc_now_iso()
        approval_item = {
            "approval_id": str(uuid4()),
            "checkpoint_id": str(approval.get("checkpoint_id", "")),
            "action": self._as_optional_str(approval.get("action")),
            "order_id": self._as_optional_str(approval.get("order_id")),
            "amount": approval.get("amount"),
            "question": self._as_optional_str(approval.get("question")),
            "reviewer": None,
            "comments": None,
            "status": "pending",
            "requested_at": now,
            "resolved_at": None,
        }
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO approvals (
                        approval_id, thread_id, checkpoint_id, action, order_id,
                        amount, question, reviewer, comments, status,
                        requested_at, resolved_at
                    )
                    VALUES (
                        %s::uuid, %s, %s::uuid, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s
                    )
                    """,
                    (
                        approval_item["approval_id"],
                        thread_id,
                        approval_item["checkpoint_id"],
                        approval_item["action"],
                        approval_item["order_id"],
                        approval_item["amount"],
                        approval_item["question"],
                        approval_item["reviewer"],
                        approval_item["comments"],
                        approval_item["status"],
                        approval_item["requested_at"],
                        approval_item["resolved_at"],
                    ),
                )
                cur.execute(
                    "UPDATE workflow_runs SET updated_at = %s WHERE thread_id = %s",
                    (now, thread_id),
                )

    def resolve_approval(
        self,
        thread_id: str,
        checkpoint_id: str,
        decision: str,
        comment: str | None,
        reviewer: str | None,
    ) -> None:
        now = _utc_now_iso()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE approvals
                    SET status = %s,
                        reviewer = %s,
                        comments = %s,
                        resolved_at = %s
                    WHERE thread_id = %s
                      AND checkpoint_id = %s::uuid
                      AND status = 'pending'
                    """,
                    (
                        "approved" if decision == "approve" else "rejected",
                        reviewer,
                        comment,
                        now,
                        thread_id,
                        checkpoint_id,
                    ),
                )
                cur.execute(
                    "UPDATE workflow_runs SET updated_at = %s WHERE thread_id = %s",
                    (now, thread_id),
                )

    @staticmethod
    def _summarize_input(input_text: str, max_len: int = 96) -> str:
        normalized = " ".join(input_text.split())
        if len(normalized) <= max_len:
            return normalized
        return f"{normalized[: max_len - 3]}..."

    @staticmethod
    def _as_optional_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _json_dumps(value: dict[str, Any]) -> str:
        import json

        return json.dumps(value)
