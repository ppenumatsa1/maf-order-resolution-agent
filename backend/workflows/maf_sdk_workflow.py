from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.models import WorkflowEvent
from tools.local_tools import fetch_order_status, fetch_policy, submit_resolution
from tools.mcp_tools import MCPKnowledgeTool
from workflows.checkpoint_store import CheckpointStore
from workflows.event_bus import EventBus
from workflows.session_memory import SessionMemoryStore


@dataclass
class WorkflowContext:
    run_id: str
    thread_id: str
    session_id: str
    customer_id: str
    user_message: str


class MafSdkSequentialWorkflow:
    """MAF-oriented workflow implementation.

    This class follows MAF patterns from `python/samples/03-workflows`:
    - `SequentialBuilder` for participant chaining
    - thread/session memory fed as context per run
    - local tools + MCP lookup wrapped around stage execution

    It intentionally preserves the same public interface as the deterministic
    workflow to keep API routes unchanged.
    """

    def __init__(
        self,
        event_bus: EventBus,
        memory_store: SessionMemoryStore,
        checkpoint_store: CheckpointStore,
        mcp_tool: MCPKnowledgeTool,
    ) -> None:
        self.event_bus = event_bus
        self.memory_store = memory_store
        self.checkpoint_store = checkpoint_store
        self.mcp_tool = mcp_tool

        # Lazy import keeps local development working even if MAF SDK is not installed.
        from agent_framework import Agent
        from agent_framework.openai import OpenAIChatClient
        from agent_framework.orchestrations import SequentialBuilder

        self._Agent = Agent
        self._OpenAIChatClient = OpenAIChatClient
        self._SequentialBuilder = SequentialBuilder

    async def start(self, context: WorkflowContext) -> None:
        self.memory_store.append_message(
            context.thread_id, "user", context.user_message
        )

        await self._emit(
            context.thread_id,
            "workflow.stage",
            {"agent": "triage", "status": "started"},
        )
        triage = await self._run_maf_sequence(
            message=context.user_message,
            context_summary=self.memory_store.summarize_context(context.thread_id),
        )
        await self._emit(
            context.thread_id,
            "workflow.stage",
            {"agent": "triage", "status": "completed", "result": {"summary": triage}},
        )

        order_id = "ord-1009" if "1009" in context.user_message.lower() else "ord-1001"
        issue_type = (
            "damaged_item"
            if "damaged" in context.user_message.lower()
            else "late_delivery"
        )
        order = fetch_order_status(order_id)
        policy = fetch_policy(issue_type)
        mcp_result = await self.mcp_tool.search(f"Policy guidance for {issue_type}")

        await self._emit(
            context.thread_id,
            "tool.call",
            {
                "local_tool": "fetch_order_status/fetch_policy",
                "mcp_tool": "search",
                "order": order.__dict__,
                "policy": policy,
                "mcp_result": mcp_result,
            },
        )

        requires_hitl = (
            order.total_amount >= 100
            or "manual_review" in policy
            or issue_type == "damaged_item"
        )
        action = (
            "offer_replacement_or_full_refund"
            if issue_type == "damaged_item"
            else "issue_partial_refund"
        )

        await self._emit(
            context.thread_id,
            "workflow.stage",
            {
                "agent": "resolution",
                "status": "completed",
                "result": {
                    "action": action,
                    "requires_hitl": requires_hitl,
                    "amount": order.total_amount,
                },
            },
        )

        if requires_hitl:
            checkpoint = self.checkpoint_store.create(
                thread_id=context.thread_id,
                state={
                    "run_id": context.run_id,
                    "session_id": context.session_id,
                    "customer_id": context.customer_id,
                    "order_id": order_id,
                    "action": action,
                    "amount": order.total_amount,
                },
            )
            await self._emit(
                context.thread_id,
                "checkpoint.created",
                {
                    "checkpoint_id": checkpoint["checkpoint_id"],
                    "reason": "approval_required",
                },
            )
            await self._emit(
                context.thread_id,
                "hitl.request",
                {
                    "checkpoint_id": checkpoint["checkpoint_id"],
                    "action": action,
                    "order_id": order_id,
                    "amount": order.total_amount,
                    "question": "Approve the proposed action?",
                },
            )
            return

        await self._complete_resolution(context.thread_id, order_id, action)

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

        thread_id = checkpoint["thread_id"]
        order_id = checkpoint["state"]["order_id"]
        action = checkpoint["state"]["action"]

        checkpoint["status"] = "approved" if decision == "approve" else "rejected"
        checkpoint["reviewer"] = reviewer
        checkpoint["comments"] = comments
        self.checkpoint_store.update(checkpoint)

        await self._emit(
            thread_id,
            "hitl.response",
            {
                "checkpoint_id": checkpoint_id,
                "decision": decision,
                "reviewer": reviewer,
                "comments": comments,
            },
        )

        if decision == "approve":
            await self._complete_resolution(thread_id, order_id, action)
        else:
            await self._emit(
                thread_id,
                "workflow.output",
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

    async def _run_maf_sequence(self, message: str, context_summary: str) -> str:
        # `OpenAIChatClient` routing follows env vars in Agent Framework.
        # For Azure, set AZURE_OPENAI_*; for OpenAI set OPENAI_*.
        client = self._OpenAIChatClient(env_file_path=os.getenv("MAF_ENV_FILE"))

        triage_agent = self._Agent(
            name="TriageAgent",
            client=client,
            instructions=(
                "Extract order issue summary in one concise sentence. "
                "If order id is missing, infer unknown."
            ),
        )
        policy_agent = self._Agent(
            name="PolicyAgent",
            client=client,
            instructions="Assess policy risk in one concise sentence.",
        )
        resolution_agent = self._Agent(
            name="ResolutionAgent",
            client=client,
            instructions="Suggest final action in one concise sentence.",
        )

        workflow = self._SequentialBuilder(
            participants=[triage_agent, policy_agent, resolution_agent],
            intermediate_output_from=[triage_agent, policy_agent],
        ).build()

        input_text = f"context:\n{context_summary}\n\nrequest:\n{message}"
        result = await workflow.run(message=input_text)
        return str(result)

    async def _complete_resolution(
        self, thread_id: str, order_id: str, action: str
    ) -> None:
        submission_id = submit_resolution(action=action, order_id=order_id)
        output = {
            "message": f"Resolution complete. Action '{action}' submitted for order {order_id}.",
            "submission_id": submission_id,
            "status": "completed",
        }
        await self._emit(thread_id, "workflow.output", output)
        self.memory_store.append_message(thread_id, "assistant", output["message"])

    async def _emit(
        self, thread_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        await self.event_bus.publish(
            WorkflowEvent(type=event_type, thread_id=thread_id, payload=payload)
        )
