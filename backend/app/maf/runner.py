from __future__ import annotations

from app.maf.workflows.order_resolution import OrderResolutionWorkflow
from app.modules.order_resolution.models import WorkflowContext
from app.modules.order_resolution.ports import WorkflowEngine, WorkflowRunRepositoryPort


class OrderResolutionMafRunner(WorkflowEngine):
    def __init__(
        self,
        *,
        workflow: OrderResolutionWorkflow,
        workflow_run_repository: WorkflowRunRepositoryPort | None = None,
    ) -> None:
        self._workflow = workflow
        self._workflow_run_repository = workflow_run_repository

    async def start(self, context: WorkflowContext) -> None:
        await self._workflow.start(context)

    async def handle_hitl_response(
        self,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> str:
        return await self._workflow.handle_hitl_response(
            checkpoint_id=checkpoint_id,
            decision=decision,
            reviewer=reviewer,
            comments=comments,
        )
