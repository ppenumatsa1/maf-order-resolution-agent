from __future__ import annotations

from dataclasses import dataclass

from app.core.telemetry import workflow_stage_span
from app.maf.tools import submit_resolution
from app.modules.order_resolution.hitl import requires_hitl, resolve_action
from app.modules.order_resolution.ports import IdempotencyRepository, SessionMemoryRepository


@dataclass(frozen=True)
class ResolutionDecision:
    action: str
    requires_approval: bool
    amount: float


class ResolutionExecutor:
    def __init__(
        self,
        *,
        idempotency_store: IdempotencyRepository,
        memory_store: SessionMemoryRepository,
    ) -> None:
        self._idempotency_store = idempotency_store
        self._memory_store = memory_store

    def decide(self, *, issue_type: str, amount: float, policy: str) -> ResolutionDecision:
        action = resolve_action(issue_type)
        return ResolutionDecision(
            action=action,
            requires_approval=requires_hitl(issue_type, amount, policy),
            amount=amount,
        )

    async def complete_resolution(
        self,
        *,
        thread_id: str,
        workflow_run_id: str,
        order_id: str,
        action: str,
        emit,
    ) -> None:
        with workflow_stage_span(
            "resolution_submit",
            {
                "workflow.thread_id": thread_id,
                "workflow.run_id": workflow_run_id,
                "workflow.order_id": order_id,
                "workflow.status": "submitting_resolution",
            },
        ):
            submission_id, _ = self._idempotency_store.execute_once(
                workflow_run_id=workflow_run_id,
                step_name="submit_resolution",
                business_id=order_id,
                operation=lambda: submit_resolution(action=action, order_id=order_id),
            )
            output = {
                "message": f"Resolution complete. Action '{action}' submitted for order {order_id}.",
                "submission_id": submission_id,
                "status": "completed",
            }
            await emit(thread_id, output)
            self._memory_store.append_message(thread_id, "assistant", output["message"])

