from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from app.core.telemetry import (
    current_trace_context,
    observe_maf_workflow_event,
    workflow_stage_span,
)
from app.infrastructure.rag import NoopRAGProvider, RAGProvider, RetrievalRequest, RetrievalResult
from app.maf.clients import (
    create_foundry_chat_client,
    get_foundry_models_config,
    has_llm_configuration,
    triage_mode_metadata,
)
from app.maf.middleware import (
    MafUsageTracker,
    WorkflowEventEnricher,
    WorkflowMiddlewareContext,
    create_chat_usage_middleware,
    execute_with_failure_event,
)
from app.maf.tools import fetch_order_status, fetch_policy, submit_resolution
from app.modules.order_resolution import events as event_types
from app.modules.order_resolution.hitl import classify_issue, requires_hitl, resolve_action
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
        await self._emit(
            context.thread_id,
            event_types.WORKFLOW_STAGE,
            {
                "agent": "triage",
                "status": "started",
                "triage_mode": self._triage_mode_metadata(),
            },
        )

        triage = await self._retry_read_operation(
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
                "result": {"summary": triage},
                "triage_mode": self._triage_mode_metadata(),
            },
        )

        message = context.user_message.lower()
        order_id = "ord-1009" if "1009" in message else "ord-1001"
        issue_type = classify_issue(message)
        order = fetch_order_status(order_id)
        policy = fetch_policy(issue_type)
        rag_result = await self._retrieve_policy_evidence(
            thread_id=context.thread_id, issue_type=issue_type
        )
        mcp_result = await self._retry_read_operation(
            lambda: self.mcp_tool.search(f"Policy guidance for {issue_type}")
        )

        await self._emit(
            context.thread_id,
            event_types.TOOL_CALL,
            {
                "local_tool": "fetch_order_status/fetch_policy",
                "mcp_tool": "search",
                "order": order.__dict__,
                "policy": policy,
                "policy_evidence_ids": [evidence.evidence_id for evidence in rag_result.evidence],
                "policy_retrieval": {
                    "provider": rag_result.provider,
                    "query_id": rag_result.query_id,
                    "count": len(rag_result.evidence),
                },
                "mcp_result": mcp_result,
            },
        )

        action = resolve_action(issue_type)
        approval_required = requires_hitl(issue_type, order.total_amount, policy)
        await self._emit(
            context.thread_id,
            event_types.WORKFLOW_STAGE,
            {
                "agent": "resolution",
                "status": "completed",
                "result": {
                    "action": action,
                    "requires_hitl": approval_required,
                    "amount": order.total_amount,
                },
            },
        )

        if approval_required:
            with workflow_stage_span(
                "hitl_waiting",
                {
                    "workflow.thread_id": context.thread_id,
                    "workflow.run_id": context.run_id,
                    "workflow.session_id": context.session_id,
                    "workflow.order_id": order_id,
                    "workflow.hitl.required": True,
                    "workflow.status": "waiting_for_approval",
                },
            ):
                checkpoint = self.checkpoint_store.create(
                    thread_id=context.thread_id,
                    state={
                        "run_id": context.run_id,
                        "session_id": context.session_id,
                        "customer_id": context.customer_id,
                        "order_id": order_id,
                        "action": action,
                        "amount": order.total_amount,
                        "telemetry_trace_context": current_trace_context(),
                    },
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
                        "action": action,
                        "order_id": order_id,
                        "amount": order.total_amount,
                        "question": "Approve the proposed action?",
                    },
                )
            return

        await self._complete_resolution(
            context.thread_id,
            context.run_id,
            order_id,
            action,
        )

    async def handle_hitl_response(
        self,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> str:
        checkpoint = self.checkpoint_store.get(checkpoint_id)
        if not checkpoint:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        with workflow_stage_span(
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
        resolved = self.checkpoint_store.try_resolve(
            checkpoint_id=checkpoint_id,
            resolved_status="approved" if decision == "approve" else "rejected",
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
            await self._complete_resolution(thread_id, workflow_run_id, order_id, action)
            return thread_id

        await self._emit(
            thread_id,
            event_types.WORKFLOW_OUTPUT,
            {
                "message": "Request rejected by reviewer. Escalating to human support specialist.",
                "status": "escalated",
            },
        )
        self.memory_store.append_message(
            thread_id,
            "assistant",
            "Request rejected by reviewer; escalated to specialist.",
        )
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
        config = get_foundry_models_config()
        if config is None:
            return f"triage_summary: {self._simple_triage_summary(message)}"

        client, credential, _ = create_foundry_chat_client(config)
        try:
            triage_agent = client.as_agent(
                name="TriageAgent",
                instructions=(
                    "Extract order issue summary in one concise sentence. "
                    "If order id is missing, infer unknown."
                ),
                default_options={"store": False},
                middleware=[
                    create_chat_usage_middleware(
                        workflow_name="order_resolution", context=workflow_context
                    )
                ],
            )
            policy_agent = client.as_agent(
                name="PolicyAgent",
                instructions="Assess policy risk in one concise sentence.",
                default_options={"store": False},
                middleware=[
                    create_chat_usage_middleware(
                        workflow_name="order_resolution", context=workflow_context
                    )
                ],
            )
            resolution_agent = client.as_agent(
                name="ResolutionAgent",
                instructions="Suggest final action in one concise sentence.",
                default_options={"store": False},
                middleware=[
                    create_chat_usage_middleware(
                        workflow_name="order_resolution", context=workflow_context
                    )
                ],
            )
            workflow = self._SequentialBuilder(
                participants=[triage_agent, policy_agent, resolution_agent],
                intermediate_output_from=[triage_agent, policy_agent],
            ).build()
            input_text = f"context:\n{context_summary}\n\nrequest:\n{message}"
            final_output: Any | None = None
            stream = workflow.run(message=input_text, stream=True)
            async for event in stream:
                observe_maf_workflow_event(event, workflow_name="order_resolution")
                usage_tracker = getattr(self, "_usage_tracker", MafUsageTracker())
                usage_tracker.observe_stream_event(
                    event, workflow_name="order_resolution", context=workflow_context
                )
                if getattr(event, "type", None) == "output":
                    final_output = getattr(event, "data", None)

            if final_output is None:
                result = await stream.get_final_response()
                outputs = result.get_outputs()
                final_output = outputs[-1] if outputs else ""
            return str(final_output)
        finally:
            close = getattr(credential, "close", None)
            if close is not None:
                await close()

    @staticmethod
    def _simple_triage_summary(message: str) -> str:
        msg = message.lower()
        issue_type = classify_issue(msg)
        order_id = "ord-1009" if "1009" in msg else "ord-1001"
        return f"order_id={order_id}; issue_type={issue_type}"

    @staticmethod
    def _has_llm_configuration() -> bool:
        return has_llm_configuration()

    @staticmethod
    def _triage_mode_metadata() -> dict[str, str]:
        return triage_mode_metadata()

    async def _complete_resolution(
        self,
        thread_id: str,
        workflow_run_id: str,
        order_id: str,
        action: str,
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
            submission_id, _ = self.idempotency_store.execute_once(
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
            await self._emit(thread_id, event_types.WORKFLOW_OUTPUT, output)
            self.memory_store.append_message(thread_id, "assistant", output["message"])

    async def _emit(self, thread_id: str, event_type: str, payload: dict[str, Any]) -> None:
        context = self._context_by_thread.get(thread_id)
        if context is not None:
            payload = self._event_enricher.enrich(context, payload)
        with workflow_stage_span(
            event_type.replace(".", "_"),
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

    async def _retrieve_policy_evidence(
        self, *, thread_id: str, issue_type: str
    ) -> RetrievalResult:
        await self._emit(
            thread_id,
            event_types.WORKFLOW_STAGE,
            {"agent": "policy_retrieval", "status": "started"},
        )
        try:
            result = await self._retry_read_operation(
                lambda: self.rag_provider.retrieve(
                    RetrievalRequest(
                        thread_id=thread_id,
                        query=f"Policy guidance for {issue_type}",
                        issue_type=issue_type,
                        top_k=3,
                    )
                )
            )
        except Exception:
            result = RetrievalResult(
                provider="rag-fallback",
                query_id=str(uuid4()),
                evidence=[],
            )

        await self._emit(
            thread_id,
            event_types.WORKFLOW_STAGE,
            {
                "agent": "policy_retrieval",
                "status": "completed",
                "result": {
                    "provider": result.provider,
                    "query_id": result.query_id,
                    "count": len(result.evidence),
                },
            },
        )
        return result
