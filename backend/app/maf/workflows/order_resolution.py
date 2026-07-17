from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.telemetry import (
    workflow_stage_span,
)
from app.infrastructure.rag import NoopRAGProvider, RAGProvider
from app.maf.clients import (
    has_llm_configuration,
    triage_mode_metadata,
)
from app.maf.executors import HitlExecutor, PolicyExecutor, ResolutionExecutor, TriageExecutor
from app.maf.middleware import (
    MafUsageTracker,
    WorkflowEventEnricher,
    WorkflowMiddlewareContext,
    execute_with_failure_event,
)
from app.modules.order_resolution import events as event_types
from app.modules.order_resolution.models import WorkflowContext, WorkflowEvent
from app.modules.order_resolution.ports import (
    CheckpointRepository,
    EventPublisher,
    IdempotencyRepository,
    McpKnowledgePort,
    SessionMemoryRepository,
)


class OrderResolutionWorkflow:
    def __init__(
        self,
        event_bus: EventPublisher,
        memory_store: SessionMemoryRepository,
        checkpoint_store: CheckpointRepository,
        mcp_tool: McpKnowledgePort,
        rag_provider: RAGProvider | None = None,
        idempotency_store: IdempotencyRepository | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.memory_store = memory_store
        self.checkpoint_store = checkpoint_store
        self.mcp_tool = mcp_tool
        self.rag_provider = rag_provider or NoopRAGProvider()
        if idempotency_store is None:
            from app.infrastructure.persistence import IdempotencyStore

            idempotency_store = IdempotencyStore()
        self.idempotency_store = idempotency_store
        self.retry_attempts = max(1, int(os.getenv("READ_RETRY_ATTEMPTS", "3")))
        self.retry_delay_seconds = max(0.0, float(os.getenv("READ_RETRY_DELAY_SECONDS", "0.2")))
        self._event_enricher = WorkflowEventEnricher()
        self._usage_tracker = MafUsageTracker()
        self._context_by_thread: dict[str, WorkflowContext] = {}

        from agent_framework.orchestrations import SequentialBuilder

        self._SequentialBuilder = SequentialBuilder
        self._triage_executor = TriageExecutor(self._SequentialBuilder, self._usage_tracker)
        self._policy_executor = PolicyExecutor(self.rag_provider, self.mcp_tool)
        self._resolution_executor = ResolutionExecutor(
            idempotency_store=self.idempotency_store,
            memory_store=self.memory_store,
        )
        self._hitl_executor = HitlExecutor(
            checkpoint_store=self.checkpoint_store,
            memory_store=self.memory_store,
        )

    async def start(self, context: WorkflowContext) -> None:
        with workflow_stage_span(
            "run",
            {
                "workflow.thread_id": context.thread_id,
                "workflow.run_id": context.run_id,
                "workflow.session_id": context.session_id,
                "workflow.customer_id": context.customer_id,
            },
        ):
            self._context_by_thread[context.thread_id] = context
            try:
                await execute_with_failure_event(
                    WorkflowMiddlewareContext(workflow="order_resolution", run=context),
                    lambda: self._start_inner(context),
                    self._emit_failure,
                )
            finally:
                self._context_by_thread.pop(context.thread_id, None)

    async def _start_inner(self, context: WorkflowContext) -> None:
        self.memory_store.append_message(context.thread_id, "user", context.user_message)
        if self._is_explanation_request(context.user_message):
            explanation = self._build_explanation(context.thread_id)
            await self._emit(
                context.thread_id,
                event_types.WORKFLOW_STAGE,
                {"agent": "explanation", "status": "completed"},
            )
            await self._emit(
                context.thread_id,
                event_types.WORKFLOW_OUTPUT,
                {"message": explanation, "status": "completed"},
            )
            self.memory_store.append_message(context.thread_id, "assistant", explanation)
            return
        await self._emit(
            context.thread_id,
            event_types.WORKFLOW_STAGE,
            {
                "agent": "triage",
                "status": "started",
                "triage_mode": self._triage_mode_metadata(),
            },
        )

        triage_result = await self._retry_read_operation(
            lambda: self._run_maf_sequence(
                context.user_message,
                self.memory_store.summarize_context(context.thread_id),
                workflow_context=context,
            )
        )
        await self._emit(
            context.thread_id,
            event_types.WORKFLOW_STAGE,
            {
                "agent": "triage",
                "status": "completed",
                "result": {"summary": triage_result},
                "triage_mode": self._triage_mode_metadata(),
            },
        )

        policy_input = await self._policy_executor.resolve_inputs(
            thread_id=context.thread_id,
            user_message=context.user_message,
            retry_read_operation=self._retry_read_operation,
            emit=lambda event_type, payload: self._emit(context.thread_id, event_type, payload),
        )

        await self._emit(
            context.thread_id,
            event_types.TOOL_CALL,
            {
                "local_tool": "fetch_order_status/fetch_policy",
                "mcp_tool": "search",
                "order": policy_input.order.__dict__,
                "policy": policy_input.policy,
                "policy_evidence_ids": [
                    evidence.evidence_id for evidence in policy_input.rag_result.evidence
                ],
                "policy_retrieval": {
                    "provider": policy_input.rag_result.provider,
                    "query_id": policy_input.rag_result.query_id,
                    "count": len(policy_input.rag_result.evidence),
                },
                "mcp_result": policy_input.mcp_result,
            },
        )

        decision = self._resolution_executor.decide(
            issue_type=policy_input.issue_type,
            amount=policy_input.order.total_amount,
            policy=policy_input.policy,
        )
        await self._emit(
            context.thread_id,
            event_types.WORKFLOW_STAGE,
            {
                "agent": "resolution",
                "status": "completed",
                "result": {
                    "action": decision.action,
                    "requires_hitl": decision.requires_approval,
                    "amount": decision.amount,
                },
            },
        )

        if decision.requires_approval:
            with workflow_stage_span(
                "hitl_waiting",
                {
                    "workflow.thread_id": context.thread_id,
                    "workflow.run_id": context.run_id,
                    "workflow.session_id": context.session_id,
                    "workflow.order_id": policy_input.order.order_id,
                    "workflow.hitl.required": True,
                    "workflow.status": "waiting_for_approval",
                },
            ):
                checkpoint = self._hitl_executor.create_checkpoint(
                    thread_id=context.thread_id,
                    run_id=context.run_id,
                    session_id=context.session_id,
                    customer_id=context.customer_id,
                    order_id=policy_input.order.order_id,
                    action=decision.action,
                    amount=policy_input.order.total_amount,
                )
                await self._emit(
                    context.thread_id,
                    event_types.CHECKPOINT_CREATED,
                    {
                        "checkpoint_id": checkpoint["checkpoint_id"],
                        "reason": "approval_required",
                    },
                )
                await self._emit(
                    context.thread_id,
                    event_types.HITL_REQUEST,
                    {
                        "checkpoint_id": checkpoint["checkpoint_id"],
                        "action": decision.action,
                        "order_id": policy_input.order.order_id,
                        "amount": policy_input.order.total_amount,
                        "question": "Approve the proposed action?",
                    },
                )
            return

        await self._resolution_executor.complete_resolution(
            thread_id=context.thread_id,
            workflow_run_id=context.run_id,
            order_id=policy_input.order.order_id,
            action=decision.action,
            emit=lambda thread_id, payload: self._emit(
                thread_id, event_types.WORKFLOW_OUTPUT, payload
            ),
        )

    async def handle_hitl_response(
        self,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> str:
        checkpoint = self._hitl_executor.load_checkpoint(checkpoint_id)
        with self._hitl_executor.resume_span(
            checkpoint_id=checkpoint_id,
            checkpoint=checkpoint,
            decision=decision,
        ):
            return await self._handle_hitl_response_inner(
                checkpoint=checkpoint,
                checkpoint_id=checkpoint_id,
                decision=decision,
                reviewer=reviewer,
                comments=comments,
            )

    async def _handle_hitl_response_inner(
        self,
        *,
        checkpoint: dict[str, Any],
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> str:
        thread_id = checkpoint["thread_id"]
        workflow_run_id = str(checkpoint["state"].get("run_id") or thread_id)
        order_id = checkpoint["state"]["order_id"]
        action = checkpoint["state"]["action"]
        resolved = self._hitl_executor.resolve_checkpoint(
            checkpoint_id=checkpoint_id,
            decision=decision,
            reviewer=reviewer,
            comments=comments,
        )
        if not resolved:
            return thread_id

        await self._emit(
            thread_id,
            event_types.HITL_RESPONSE,
            {
                "checkpoint_id": checkpoint_id,
                "decision": decision,
                "reviewer": reviewer,
                "comments": comments,
            },
        )

        if decision == "approve":
            await self._resolution_executor.complete_resolution(
                thread_id=thread_id,
                workflow_run_id=workflow_run_id,
                order_id=order_id,
                action=action,
                emit=lambda emit_thread, payload: self._emit(
                    emit_thread, event_types.WORKFLOW_OUTPUT, payload
                ),
            )
            return thread_id

        await self._emit(
            thread_id,
            event_types.WORKFLOW_OUTPUT,
            {
                "message": "Request rejected by reviewer. Escalating to human support specialist.",
                "status": "escalated",
            },
        )
        self._hitl_executor.record_rejection_message(thread_id)
        return thread_id

    async def _run_maf_sequence(
        self,
        message: str,
        context_summary: str,
        *,
        workflow_context: WorkflowContext | None = None,
    ) -> str:
        if workflow_context is None:
            workflow_context = WorkflowContext(
                run_id="adhoc",
                thread_id="adhoc",
                session_id="adhoc",
                customer_id="adhoc",
                user_message=message,
            )
        triage_executor = getattr(self, "_triage_executor", None)
        if triage_executor is None:
            sequential_builder = getattr(self, "_SequentialBuilder", None)
            if sequential_builder is None:
                from agent_framework.orchestrations import SequentialBuilder

                sequential_builder = SequentialBuilder
                self._SequentialBuilder = sequential_builder
            triage_executor = TriageExecutor(
                sequential_builder,
                getattr(self, "_usage_tracker", MafUsageTracker()),
            )
        result = await triage_executor.run(
            message=message,
            context_summary=context_summary,
            workflow_context=workflow_context,
        )
        return result.summary

    @staticmethod
    def _simple_triage_summary(message: str) -> str:
        return TriageExecutor.simple_summary(message)

    @staticmethod
    def _has_llm_configuration() -> bool:
        return has_llm_configuration()

    @staticmethod
    def _triage_mode_metadata() -> dict[str, str]:
        return triage_mode_metadata()

    async def _emit(self, thread_id: str, event_type: str, payload: dict[str, Any]) -> None:
        context = self._context_by_thread.get(thread_id)
        if context is not None:
            payload = self._event_enricher.enrich(context, payload)
        span_stage = event_type.replace(".", "_")
        if event_type == event_types.WORKFLOW_STAGE:
            agent = str(payload.get("agent") or "").strip()
            status = str(payload.get("status") or "").strip()
            if agent and status:
                span_stage = f"stage.{agent}.{status}"
            elif agent:
                span_stage = f"stage.{agent}"
        with workflow_stage_span(
            span_stage,
            {
                "event.type": event_type,
                "workflow.thread_id": thread_id,
                "workflow.agent": payload.get("agent"),
                "workflow.status": payload.get("status"),
            },
        ):
            await self.event_bus.publish(
                WorkflowEvent(type=event_type, thread_id=thread_id, payload=payload)
            )

    async def _emit_failure(self, context: WorkflowContext, exc: Exception) -> None:
        await self._emit(
            context.thread_id,
            event_types.WORKFLOW_FAILED,
            {
                "status": "failed",
                "code": exc.__class__.__name__,
                "message": str(exc),
            },
        )

    async def _retry_read_operation(self, operation: Callable[[], Awaitable[Any]]) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                return await operation()
            except Exception as exc:
                last_error = exc
                if attempt == self.retry_attempts:
                    break
                await asyncio.sleep(self.retry_delay_seconds * attempt)

        if last_error:
            raise last_error
        raise RuntimeError("Read operation failed without raising an exception.")

    @staticmethod
    def _is_explanation_request(message: str) -> bool:
        lowered = message.lower()
        return "why" in lowered and "resolution" in lowered

    def _build_explanation(self, thread_id: str) -> str:
        messages = self.memory_store.get_messages(thread_id)
        for item in reversed(messages[:-1]):
            role = str(item.get("role", "")).strip().lower()
            content = str(item.get("content", "")).strip()
            if role == "assistant" and content:
                return (
                    "The resolution was selected from order status and policy checks. "
                    f"Previous result: {content}"
                )
        return (
            "The resolution is selected from order status, policy evidence, "
            "and HITL thresholds for high-risk or damaged-item cases."
        )
