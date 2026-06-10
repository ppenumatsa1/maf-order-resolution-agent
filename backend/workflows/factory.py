from __future__ import annotations

from app.core.config import AppConfig
from app.modules.order_resolution.ports import (
    CheckpointRepository,
    EventPublisher,
    McpKnowledgePort,
    SessionMemoryRepository,
)
from workflows.maf_sdk_workflow import MafSdkSequentialWorkflow
from workflows.rag.core import RAGProvider


def create_workflow(
    *,
    config: AppConfig,
    event_bus: EventPublisher,
    memory_store: SessionMemoryRepository,
    checkpoint_store: CheckpointRepository,
    mcp_tool: McpKnowledgePort,
    rag_provider: RAGProvider,
):
    if config.workflow_mode == "maf_sdk":
        return MafSdkSequentialWorkflow(
            event_bus=event_bus,
            memory_store=memory_store,
            checkpoint_store=checkpoint_store,
            mcp_tool=mcp_tool,
            rag_provider=rag_provider,
        )

    if config.workflow_mode == "foundry_hosted":
        raise NotImplementedError(
            "WORKFLOW_MODE=foundry_hosted is not implemented yet in this phase."
        )

    raise ValueError(f"Unsupported workflow mode: {config.workflow_mode}")
