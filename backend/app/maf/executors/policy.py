from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.infrastructure.rag import RAGProvider, RetrievalRequest, RetrievalResult
from app.maf.tools import OrderStatus, fetch_order_status, fetch_policy
from app.modules.order_resolution.hitl import classify_issue
from app.modules.order_resolution.ports import McpKnowledgePort


@dataclass(frozen=True)
class PolicyResolutionInput:
    issue_type: str
    order: OrderStatus
    policy: str
    rag_result: RetrievalResult
    mcp_result: dict[str, object]


class PolicyExecutor:
    def __init__(self, rag_provider: RAGProvider, mcp_tool: McpKnowledgePort) -> None:
        self._rag_provider = rag_provider
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
        try:
            rag_result = await retry_read_operation(
                lambda: self._rag_provider.retrieve(
                    RetrievalRequest(
                        thread_id=thread_id,
                        query=f"Policy guidance for {issue_type}",
                        issue_type=issue_type,
                        top_k=3,
                    )
                )
            )
        except Exception:
            rag_result = RetrievalResult(
                provider="rag-fallback",
                query_id=str(uuid4()),
                evidence=[],
            )
        await emit(
            "workflow.stage",
            {
                "agent": "policy_retrieval",
                "status": "completed",
                "result": {
                    "provider": rag_result.provider,
                    "query_id": rag_result.query_id,
                    "count": len(rag_result.evidence),
                },
            },
        )
        mcp_result = await retry_read_operation(
            lambda: self._mcp_tool.search(f"Policy guidance for {issue_type}")
        )
        return PolicyResolutionInput(
            issue_type=issue_type,
            order=order,
            policy=policy,
            rag_result=rag_result,
            mcp_result=mcp_result,
        )
