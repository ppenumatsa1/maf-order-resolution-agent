from __future__ import annotations

import pytest
from app.core.config import AppConfig
from app.foundry.workflow import FoundryHostedWorkflow
from app.infrastructure.events import EventBus
from app.infrastructure.rag import NoopRAGProvider
from app.maf.factory import create_workflow


class _MemoryStore:
    def get_messages(self, thread_id: str) -> list[dict[str, object]]:
        return []

    def append_message(self, thread_id: str, role: str, content: str) -> None:
        return None

    def summarize_context(self, thread_id: str, max_messages: int = 8) -> str:
        return ""


class _CheckpointStore:
    def create(self, thread_id: str, state: dict[str, object]) -> dict[str, object]:
        return {"checkpoint_id": "cp-1", "thread_id": thread_id, "state": state}

    def get(self, checkpoint_id: str) -> dict[str, object] | None:
        return None

    def try_resolve(
        self,
        *,
        checkpoint_id: str,
        resolved_status: str,
        reviewer: str,
        comments: str | None,
    ) -> bool:
        return True


class _McpTool:
    async def search(self, query: str) -> dict[str, object]:
        return {"source": "test", "query": query}


def test_create_workflow_uses_foundry_hosted_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOUNDRY_HOSTED_INVOCATIONS_URL", "https://example.test/invocations")
    workflow = create_workflow(
        config=AppConfig(
            workflow_mode="foundry_hosted",
            store_provider="postgres",
            rag_provider="pgvector",
            memory_provider="postgres",
        ),
        event_bus=EventBus(),
        memory_store=_MemoryStore(),
        checkpoint_store=_CheckpointStore(),
        mcp_tool=_McpTool(),
        rag_provider=NoopRAGProvider(),
    )
    assert isinstance(workflow, FoundryHostedWorkflow)


def test_create_workflow_foundry_mode_requires_invocations_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOUNDRY_HOSTED_INVOCATIONS_URL", raising=False)
    with pytest.raises(ValueError, match="FOUNDRY_HOSTED_INVOCATIONS_URL"):
        create_workflow(
            config=AppConfig(
                workflow_mode="foundry_hosted",
                store_provider="postgres",
                rag_provider="pgvector",
                memory_provider="postgres",
            ),
            event_bus=EventBus(),
            memory_store=_MemoryStore(),
            checkpoint_store=_CheckpointStore(),
            mcp_tool=_McpTool(),
            rag_provider=NoopRAGProvider(),
        )
