from __future__ import annotations

from app.core.config import get_config
from app.core.database import postgres_db
from app.core.telemetry import record_workflow_event
from app.infrastructure.events import EventBus
from app.infrastructure.mcp import MCPKnowledgeTool
from app.infrastructure.persistence import CheckpointStore, WorkflowRunRepository
from app.infrastructure.persistence.session_memory import create_memory_store
from app.maf.factory import create_workflow
from app.modules.order_resolution.projections import WorkflowRunEventProjector
from app.modules.order_resolution.service import OrderResolutionService

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
workflow_run_event_projector = WorkflowRunEventProjector(workflow_run_repository)

event_bus.add_listener(workflow_run_event_projector.sync_event_to_run)
event_bus.add_listener(record_workflow_event)

workflow = create_workflow(
    config=config,
    event_bus=event_bus,
    memory_store=memory_store,
    checkpoint_store=checkpoint_store,
    mcp_tool=mcp_tool,
    workflow_run_repository=workflow_run_repository,
)

order_resolution_service = OrderResolutionService(
    workflow=workflow,
    workflow_run_repository=workflow_run_repository,
)
