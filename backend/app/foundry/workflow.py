from __future__ import annotations

from numbers import Number
from typing import Protocol

from app.foundry.models import FoundryEventPayload, FoundryInvocationResponse
from app.modules.order_resolution import events as event_types
from app.modules.order_resolution.models import WorkflowContext, WorkflowEvent
from app.modules.order_resolution.ports import EventPublisher, WorkflowRunRepositoryPort


class FoundryInvocationPort(Protocol):
    async def start_workflow(self, context: WorkflowContext) -> FoundryInvocationResponse: ...

    async def resume_hitl(
        self,
        *,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
        thread_id: str | None = None,
        action: str | None = None,
        order_id: str | None = None,
        amount: float | int | None = None,
    ) -> FoundryInvocationResponse: ...


class FoundryHostedWorkflow:
    def __init__(
        self,
        *,
        event_bus: EventPublisher,
        client: FoundryInvocationPort,
        workflow_run_repository: WorkflowRunRepositoryPort | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.client = client
        self.workflow_run_repository = workflow_run_repository
        self._canonical_thread_by_hosted: dict[str, str] = {}
        self._approval_context_by_checkpoint: dict[str, dict[str, object]] = {}

    async def start(self, context: WorkflowContext) -> None:
        await self._publish_invocation_stage(
            thread_id=context.thread_id,
            status="started",
            operation="start_workflow",
            details={"workflow_run_id": context.run_id, "session_id": context.session_id},
        )
        try:
            response = await self.client.start_workflow(context)
            self._remember_thread_mapping(
                hosted_thread_id=response.thread_id,
                canonical_thread_id=context.thread_id,
            )
            await self._publish_invocation_stage(
                thread_id=context.thread_id,
                status="completed",
                operation="start_workflow",
                details={
                    "workflow_run_id": context.run_id,
                    "session_id": context.session_id,
                    "hosted_thread_id": response.thread_id,
                    "response_status": response.status,
                    "hosted_event_count": len(response.events),
                },
            )
            await self._publish_response_events(response, canonical_thread_id=context.thread_id)
        except Exception as exc:
            await self.event_bus.publish(
                WorkflowEvent(
                    type=event_types.WORKFLOW_FAILED,
                    thread_id=context.thread_id,
                    payload={
                        "stage": "foundry_invocations",
                        "error": str(exc),
                        "workflow_run_id": context.run_id,
                        "session_id": context.session_id,
                    },
                )
            )
            raise

    async def handle_hitl_response(
        self,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> str:
        resume_context = self._approval_context_by_checkpoint.get(checkpoint_id)
        if resume_context is None and self.workflow_run_repository is not None:
            resume_context = self.workflow_run_repository.get_pending_approval_context(
                checkpoint_id
            )
        response = await self.client.resume_hitl(
            checkpoint_id=checkpoint_id,
            decision=decision,
            reviewer=reviewer,
            comments=comments,
            thread_id=(
                str(resume_context.get("thread_id"))
                if isinstance(resume_context, dict)
                and isinstance(resume_context.get("thread_id"), str)
                else None
            ),
            action=(
                str(resume_context.get("action"))
                if isinstance(resume_context, dict)
                and isinstance(resume_context.get("action"), str)
                else None
            ),
            order_id=(
                str(resume_context.get("order_id"))
                if isinstance(resume_context, dict)
                and isinstance(resume_context.get("order_id"), str)
                else None
            ),
            amount=(
                float(resume_context.get("amount"))
                if isinstance(resume_context, dict)
                and isinstance(resume_context.get("amount"), Number)
                else None
            ),
        )
        canonical_thread_id = self._canonical_thread_by_hosted.get(response.thread_id)
        await self._publish_invocation_stage(
            thread_id=canonical_thread_id or response.thread_id,
            status="completed",
            operation="resume_hitl",
            details={
                "checkpoint_id": checkpoint_id,
                "decision": decision,
                "response_status": response.status,
                "hosted_event_count": len(response.events),
            },
        )
        await self._publish_response_events(response, canonical_thread_id=canonical_thread_id)
        return canonical_thread_id or response.thread_id

    async def _publish_response_events(
        self,
        response: FoundryInvocationResponse,
        *,
        canonical_thread_id: str | None = None,
    ) -> None:
        if canonical_thread_id is not None:
            self._remember_thread_mapping(
                hosted_thread_id=response.thread_id,
                canonical_thread_id=canonical_thread_id,
            )

        if not any(event.type == event_types.TOOL_CALL for event in response.events):
            await self.event_bus.publish(
                WorkflowEvent(
                    type=event_types.TOOL_CALL,
                    thread_id=canonical_thread_id or response.thread_id,
                    payload={
                        "local_tool": "foundry_hosted.invocations",
                        "provider": "foundry_hosted",
                        "response_status": response.status,
                        "hosted_event_count": len(response.events),
                    },
                )
            )

        for event in response.events:
            workflow_event = self._to_workflow_event(
                event,
                fallback_thread_id=response.thread_id,
                canonical_thread_id=canonical_thread_id,
            )
            self._remember_approval_context(workflow_event)
            await self.event_bus.publish(workflow_event)

    def _to_workflow_event(
        self,
        event: FoundryEventPayload,
        *,
        fallback_thread_id: str,
        canonical_thread_id: str | None = None,
    ) -> WorkflowEvent:
        event_thread_id = event.thread_id or fallback_thread_id
        canonical_event_thread_id = (
            canonical_thread_id
            or self._canonical_thread_by_hosted.get(event_thread_id)
            or event_thread_id
        )
        workflow_event = WorkflowEvent(
            type=event.type,
            thread_id=canonical_event_thread_id,
            payload=event.payload,
        )
        if event.id:
            workflow_event.id = event.id
        if event.timestamp:
            workflow_event.timestamp = event.timestamp
        return workflow_event

    def _remember_thread_mapping(self, *, hosted_thread_id: str, canonical_thread_id: str) -> None:
        self._canonical_thread_by_hosted[hosted_thread_id] = canonical_thread_id

    def _remember_approval_context(self, event: WorkflowEvent) -> None:
        if event.type != event_types.HITL_REQUEST:
            return
        checkpoint_id = event.payload.get("checkpoint_id")
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            return
        self._approval_context_by_checkpoint[checkpoint_id] = {
            "thread_id": event.thread_id,
            "action": event.payload.get("action"),
            "order_id": event.payload.get("order_id"),
            "amount": event.payload.get("amount"),
        }

    async def _publish_invocation_stage(
        self,
        *,
        thread_id: str,
        status: str,
        operation: str,
        details: dict[str, object],
    ) -> None:
        await self.event_bus.publish(
            WorkflowEvent(
                type=event_types.WORKFLOW_STAGE,
                thread_id=thread_id,
                payload={
                    "agent": "foundry_invocations",
                    "status": status,
                    "operation": operation,
                    **details,
                },
            )
        )
