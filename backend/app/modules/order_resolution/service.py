from __future__ import annotations

from uuid import uuid4

from app.api.v1.schemas.chat import ChatRunRequest, ChatRunResponse
from app.api.v1.schemas.hitl import HitlResponseRequest, HitlResponseResult
from app.modules.order_resolution.models import WorkflowContext
from app.modules.order_resolution.ports import WorkflowEngine, WorkflowRunRepositoryPort


class OrderResolutionService:
    def __init__(
        self,
        *,
        workflow: WorkflowEngine,
        workflow_run_repository: WorkflowRunRepositoryPort,
    ) -> None:
        self._workflow = workflow
        self._workflow_run_repository = workflow_run_repository

    async def start_chat_run(self, request: ChatRunRequest) -> ChatRunResponse:
        run_id = str(uuid4())
        thread_id = request.thread_id or str(uuid4())
        session_id = request.session_id or thread_id

        context = WorkflowContext(
            run_id=run_id,
            thread_id=thread_id,
            session_id=session_id,
            customer_id=request.customer_id,
            user_message=request.message,
        )
        self._workflow_run_repository.create_workflow_run(
            thread_id=thread_id,
            input_text=request.message,
            session_id=session_id,
            customer_id=request.customer_id,
        )
        await self._workflow.start(context)

        return ChatRunResponse(run_id=run_id, thread_id=thread_id)

    async def respond_hitl(self, request: HitlResponseRequest) -> HitlResponseResult:
        thread_id = await self._workflow.handle_hitl_response(
            checkpoint_id=request.checkpoint_id,
            decision=request.decision,
            reviewer=request.reviewer,
            comments=request.comments,
        )
        return HitlResponseResult(
            accepted=True,
            checkpoint_id=request.checkpoint_id,
            thread_id=thread_id,
        )
