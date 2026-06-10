from __future__ import annotations

from app.config import AppConfig
from tools.mcp_tools import MCPKnowledgeTool
from workflows.checkpoint_store import CheckpointStore
from workflows.event_bus import EventBus
from workflows.maf_sdk_workflow import MafSdkSequentialWorkflow
from workflows.rag.core import RAGProvider
from workflows.session_memory import SessionMemoryProvider


def create_workflow(
    *,
    config: AppConfig,
    event_bus: EventBus,
    memory_store: SessionMemoryProvider,
    checkpoint_store: CheckpointStore,
    mcp_tool: MCPKnowledgeTool,
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
