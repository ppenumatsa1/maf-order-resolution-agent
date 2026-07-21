from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.maf.tools import OrderStatus, fetch_order_status, fetch_policy
from app.modules.order_resolution.hitl import classify_issue
from app.modules.order_resolution.ports import McpKnowledgePort


@dataclass(frozen=True)
class PolicyResolutionInput:
    issue_type: str
    order: OrderStatus
    policy: str
    policy_query_id: str
    mcp_result: dict[str, object]


class PolicyExecutor:
    def __init__(self, mcp_tool: McpKnowledgePort) -> None:
        self._mcp_tool = mcp_tool

    async def resolve_inputs(
        self,
        *,
        thread_id: str,
        user_message: str,
        retry_read_operation,
        emit: Callable[[str, dict[str, Any]], Awaitable[None]],
    ) -> PolicyResolutionInput:
        message = user_message.lower()
        order_id = "ord-1009" if "1009" in message else "ord-1001"
        issue_type = classify_issue(message)
        order = fetch_order_status(order_id)
        policy = fetch_policy(issue_type)
        await emit(
            "workflow.stage",
            {"agent": "policy_retrieval", "status": "started"},
        )
        mcp_result = await retry_read_operation(
            lambda: self._mcp_tool.search(f"Policy guidance for {issue_type}")
        )
        await emit(
            "workflow.stage",
            {
                "agent": "policy_retrieval",
                "status": "completed",
                "result": {
                    "provider": "mcp",
                    "query_id": f"mcp:{thread_id}:{issue_type}",
                    "count": len(mcp_result.get("results", [])),
                },
            },
        )
        return PolicyResolutionInput(
            issue_type=issue_type,
            order=order,
            policy=policy,
            policy_query_id=f"mcp:{thread_id}:{issue_type}",
            mcp_result=mcp_result,
        )
