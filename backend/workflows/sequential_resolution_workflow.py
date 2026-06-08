from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.models import WorkflowEvent
from observability.otel import get_tracer
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


class SequentialResolutionWorkflow:
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
        self.tracer = get_tracer("workflow.sequential")

    async def start(self, context: WorkflowContext) -> None:
        with self.tracer.start_as_current_span("workflow.start"):
            self.memory_store.append_message(
                context.thread_id, "user", context.user_message
            )

            triage = await self._triage_agent(context)
            policy = await self._policy_agent(context, triage)
            resolution = await self._resolution_agent(context, triage, policy)

            if resolution["requires_hitl"]:
                checkpoint = self.checkpoint_store.create(
                    thread_id=context.thread_id,
                    state={
                        "run_id": context.run_id,
                        "session_id": context.session_id,
                        "customer_id": context.customer_id,
                        "triage": triage,
                        "policy": policy,
                        "resolution": resolution,
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
                        "action": resolution["action"],
                        "order_id": triage["order_id"],
                        "amount": resolution["amount"],
                        "question": "Approve the proposed action?",
                    },
                )
                return

            await self._complete_resolution(
                context.thread_id, triage["order_id"], resolution["action"]
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

        state = checkpoint["state"]
        thread_id = checkpoint["thread_id"]
        resolution = state["resolution"]
        order_id = state["triage"]["order_id"]

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
            await self._complete_resolution(thread_id, order_id, resolution["action"])
            return thread_id

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

    async def _triage_agent(self, context: WorkflowContext) -> dict[str, Any]:
        with self.tracer.start_as_current_span("agent.triage"):
            await self._emit(
                context.thread_id,
                "workflow.stage",
                {"agent": "triage", "status": "started"},
            )
            order_id = self._extract_order_id(context.user_message)
            issue_type = self._classify_issue(context.user_message)
            summary = self.memory_store.summarize_context(context.thread_id)
            triage = {
                "order_id": order_id,
                "issue_type": issue_type,
                "context_summary": summary,
            }
            await self._emit(
                context.thread_id,
                "workflow.stage",
                {"agent": "triage", "status": "completed", "result": triage},
            )
            return triage

    async def _policy_agent(
        self, context: WorkflowContext, triage: dict[str, Any]
    ) -> dict[str, Any]:
        with self.tracer.start_as_current_span("agent.policy"):
            await self._emit(
                context.thread_id,
                "workflow.stage",
                {"agent": "policy", "status": "started"},
            )
            order = fetch_order_status(triage["order_id"])
            policy = fetch_policy(triage["issue_type"])
            mcp_result = await self.mcp_tool.search(
                f"Customer support policy for {triage['issue_type']} and delayed orders"
            )
            tool_event = {
                "local_tool": "fetch_order_status/fetch_policy",
                "mcp_tool": "search",
                "order": order.__dict__,
                "policy": policy,
                "mcp_result": mcp_result,
            }
            await self._emit(context.thread_id, "tool.call", tool_event)
            stage_result = {
                "order_state": order.state,
                "amount": order.total_amount,
                "policy": policy,
            }
            await self._emit(
                context.thread_id,
                "workflow.stage",
                {"agent": "policy", "status": "completed", "result": stage_result},
            )
            return stage_result

    async def _resolution_agent(
        self,
        context: WorkflowContext,
        triage: dict[str, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        with self.tracer.start_as_current_span("agent.resolution"):
            await self._emit(
                context.thread_id,
                "workflow.stage",
                {"agent": "resolution", "status": "started"},
            )
            action = "issue_partial_refund"
            requires_hitl = (
                policy["amount"] >= 100 or "manual_review" in policy["policy"]
            )
            if triage["issue_type"] == "damaged_item":
                action = "offer_replacement_or_full_refund"
                requires_hitl = True

            resolution = {
                "action": action,
                "requires_hitl": requires_hitl,
                "amount": policy["amount"],
            }
            await self._emit(
                context.thread_id,
                "workflow.stage",
                {"agent": "resolution", "status": "completed", "result": resolution},
            )
            return resolution

    async def _complete_resolution(
        self, thread_id: str, order_id: str, action: str
    ) -> None:
        with self.tracer.start_as_current_span("workflow.complete"):
            submission_id = submit_resolution(action=action, order_id=order_id)
            output = {
                "message": f"Resolution complete. Action '{action}' submitted for order {order_id}.",
                "submission_id": submission_id,
                "status": "completed",
            }
            await self._emit(thread_id, "workflow.output", output)
            self.memory_store.append_message(thread_id, "assistant", output["message"])

    @staticmethod
    def _extract_order_id(message: str) -> str:
        match = re.search(r"(ord[-_ ]?\d{3,})", message.lower())
        if not match:
            return "ord-1009"
        raw = match.group(1).replace(" ", "").replace("_", "-")
        return raw

    @staticmethod
    def _classify_issue(message: str) -> str:
        msg = message.lower()
        if "damage" in msg or "broken" in msg:
            return "damaged_item"
        if "wrong" in msg:
            return "wrong_item"
        return "late_delivery"

    async def _emit(
        self, thread_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        await self.event_bus.publish(
            WorkflowEvent(type=event_type, thread_id=thread_id, payload=payload)
        )
