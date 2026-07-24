from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from app.api.v1.schemas.chat import ChatRunRequest, ChatRunResponse
from app.api.v1.schemas.hitl import HitlResponseRequest, HitlResponseResult
from app.modules.order_resolution.models import WorkflowContext
from app.modules.order_resolution.ports import (
    ResponsesWorkflowPort,
    WorkflowEngine,
    WorkflowRunRepositoryPort,
)


class OrderResolutionService:
    def __init__(
        self,
        *,
        workflow: WorkflowEngine,
        workflow_run_repository: WorkflowRunRepositoryPort,
        responses_client: ResponsesWorkflowPort | None = None,
    ) -> None:
        self._workflow = workflow
        self._workflow_run_repository = workflow_run_repository
        self._responses_client = responses_client

    async def start_chat_run(self, request: ChatRunRequest) -> ChatRunResponse:
        run_id = str(uuid4())
        thread_id = request.thread_id or str(uuid4())
        session_id = request.session_id or thread_id

        if self._responses_client is not None:
            idempotency_key = request.idempotency_key or run_id
            request_hash = hashlib.sha256(
                json.dumps(
                    {
                        "message": request.message,
                        "thread_id": thread_id,
                        "session_id": session_id,
                        "customer_id": request.customer_id,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            dispatch = self._workflow_run_repository.create_or_get_responses_dispatch(
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                run_id=run_id,
                thread_id=thread_id,
            )
            if dispatch["status"] != "pending":
                return ChatRunResponse(
                    run_id=str(dispatch["run_id"]),
                    thread_id=str(dispatch["thread_id"]),
                )
            try:
                resolved_thread_id = await self._responses_client.start_workflow(
                    thread_id=thread_id,
                    message=request.message,
                )
            except Exception:
                self._workflow_run_repository.update_responses_dispatch_status(
                    idempotency_key, "unknown"
                )
                raise
            if resolved_thread_id != thread_id:
                self._workflow_run_repository.update_responses_dispatch_thread(
                    idempotency_key, resolved_thread_id
                )
            self._workflow_run_repository.update_responses_dispatch_status(
                idempotency_key, "submitted"
            )
            return ChatRunResponse(run_id=run_id, thread_id=resolved_thread_id)

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
        if self._responses_client is not None:
            pending_context = self._workflow_run_repository.get_pending_approval_context(
                request.checkpoint_id
            )
            if pending_context is None:
                raise ValueError(f"Pending approval not found: {request.checkpoint_id}")
            thread_id = str(pending_context["thread_id"])
            await self._responses_client.respond_to_hitl(
                thread_id=thread_id,
                checkpoint_id=request.checkpoint_id,
                decision=request.decision,
            )
            return HitlResponseResult(
                accepted=True,
                checkpoint_id=request.checkpoint_id,
                thread_id=thread_id,
            )

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
