from __future__ import annotations

from typing import Any

from app.core.telemetry import current_trace_context, workflow_stage_span
from app.modules.order_resolution.ports import CheckpointRepository, SessionMemoryRepository


class HitlExecutor:
    def __init__(
        self,
        *,
        checkpoint_store: CheckpointRepository,
        memory_store: SessionMemoryRepository,
    ) -> None:
        self._checkpoint_store = checkpoint_store
        self._memory_store = memory_store

    def create_checkpoint(
        self,
        *,
        thread_id: str,
        run_id: str,
        session_id: str,
        customer_id: str,
        order_id: str,
        action: str,
        amount: float,
    ) -> dict[str, Any]:
        return self._checkpoint_store.create(
            thread_id=thread_id,
            state={
                "run_id": run_id,
                "session_id": session_id,
                "customer_id": customer_id,
                "order_id": order_id,
                "action": action,
                "amount": amount,
                "telemetry_trace_context": current_trace_context(),
            },
        )

    def load_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        checkpoint = self._checkpoint_store.get(checkpoint_id)
        if not checkpoint:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")
        return checkpoint

    def resolve_checkpoint(
        self,
        *,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> bool:
        return self._checkpoint_store.try_resolve(
            checkpoint_id=checkpoint_id,
            resolved_status="approved" if decision == "approve" else "rejected",
            reviewer=reviewer,
            comments=comments,
        )

    def resume_span(
        self,
        *,
        checkpoint_id: str,
        checkpoint: dict[str, Any],
        decision: str,
    ):
        return workflow_stage_span(
            "hitl_resume",
            {
                "workflow.thread_id": checkpoint["thread_id"],
                "workflow.run_id": checkpoint["state"].get("run_id"),
                "workflow.session_id": checkpoint["state"].get("session_id"),
                "workflow.checkpoint_id": checkpoint_id,
                "workflow.order_id": checkpoint["state"].get("order_id"),
                "workflow.hitl.decision": decision,
            },
            parent_trace_context=checkpoint["state"].get("telemetry_trace_context"),
        )

    def record_rejection_message(self, thread_id: str) -> None:
        self._memory_store.append_message(
            thread_id,
            "assistant",
            "Request rejected by reviewer; escalated to specialist.",
        )
