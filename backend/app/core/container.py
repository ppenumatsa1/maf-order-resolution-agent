from __future__ import annotations

from app.core.config import get_config
from app.core.database import postgres_db
from app.infrastructure.events import EventBus
from app.infrastructure.mcp import MCPKnowledgeTool
from app.infrastructure.persistence import CheckpointStore, WorkflowRunRepository
from app.infrastructure.persistence.session_memory import create_memory_store
from app.infrastructure.rag import create_rag_provider
from app.modules.order_resolution.projections import WorkflowRunEventProjector
from app.modules.order_resolution.service import OrderResolutionService
from workflows.factory import create_workflow

postgres_db.ensure_schema()
config = get_config()
if config.store_provider != "postgres":
    raise RuntimeError(
        "Store provider switching is not implemented yet. Use STORE_PROVIDER=postgres."
    )

event_bus = EventBus()
workflow_run_repository = WorkflowRunRepository()
memory_store = create_memory_store(config.memory_provider)
checkpoint_store = CheckpointStore()
mcp_tool = MCPKnowledgeTool()
rag_provider = create_rag_provider(config.rag_provider)
workflow_run_event_projector = WorkflowRunEventProjector(workflow_run_repository)

event_bus.add_listener(workflow_run_event_projector.sync_event_to_run)

try:
    workflow = create_workflow(
        config=config,
        event_bus=event_bus,
        memory_store=memory_store,
        checkpoint_store=checkpoint_store,
        mcp_tool=mcp_tool,
        rag_provider=rag_provider,
    )
except NotImplementedError as exc:
    raise RuntimeError(
        "Unsupported runtime configuration: foundry_hosted mode is not available yet."
    ) from exc

order_resolution_service = OrderResolutionService(
    workflow=workflow,
    workflow_run_repository=workflow_run_repository,
)
