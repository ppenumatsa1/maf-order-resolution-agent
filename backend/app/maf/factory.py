from __future__ import annotations

from app.core.config import AppConfig
from app.infrastructure.rag import RAGProvider
from app.maf.workflows.order_resolution import OrderResolutionWorkflow
from app.modules.order_resolution.ports import (
    CheckpointRepository,
    EventPublisher,
    IdempotencyRepository,
    McpKnowledgePort,
    SessionMemoryRepository,
)


def create_workflow(
    *,
    config: AppConfig,
    event_bus: EventPublisher,
    memory_store: SessionMemoryRepository,
    checkpoint_store: CheckpointRepository,
    mcp_tool: McpKnowledgePort,
    rag_provider: RAGProvider,
    idempotency_store: IdempotencyRepository | None = None,
) -> OrderResolutionWorkflow:
    if config.workflow_mode == "maf_sdk":
        return OrderResolutionWorkflow(
            event_bus=event_bus,
            memory_store=memory_store,
            checkpoint_store=checkpoint_store,
            mcp_tool=mcp_tool,
            rag_provider=rag_provider,
            idempotency_store=idempotency_store,
        )

    if config.workflow_mode == "foundry_hosted":
        raise NotImplementedError(
            "WORKFLOW_MODE=foundry_hosted is not implemented yet in this phase."
        )

    raise ValueError(f"Unsupported workflow mode: {config.workflow_mode}")


__all__ = ["create_workflow"]
