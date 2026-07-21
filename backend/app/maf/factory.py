from __future__ import annotations

from app.core.config import AppConfig
from app.maf.runner import OrderResolutionMafRunner
from app.maf.workflows.order_resolution import OrderResolutionWorkflow
from app.modules.order_resolution.ports import (
    CheckpointRepository,
    EventPublisher,
    IdempotencyRepository,
    McpKnowledgePort,
    SessionMemoryRepository,
    WorkflowEngine,
    WorkflowRunRepositoryPort,
)


def create_workflow(
    *,
    config: AppConfig,
    event_bus: EventPublisher,
    memory_store: SessionMemoryRepository,
    checkpoint_store: CheckpointRepository,
    mcp_tool: McpKnowledgePort,
    idempotency_store: IdempotencyRepository | None = None,
    workflow_run_repository: WorkflowRunRepositoryPort | None = None,
) -> WorkflowEngine:
    workflow = OrderResolutionWorkflow(
        event_bus=event_bus,
        memory_store=memory_store,
        checkpoint_store=checkpoint_store,
        mcp_tool=mcp_tool,
        idempotency_store=idempotency_store,
    )
    return OrderResolutionMafRunner(
        workflow=workflow,
        workflow_run_repository=workflow_run_repository,
    )


__all__ = ["create_workflow"]
