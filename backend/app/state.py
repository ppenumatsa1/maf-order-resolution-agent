from __future__ import annotations

from app.config import get_config
from app.db import postgres_db
from app.models import WorkflowEvent
from app.workflow_run_repository import WorkflowRunRepository
from tools.mcp_tools import MCPKnowledgeTool
from workflows.checkpoint_store import CheckpointStore
from workflows.event_bus import EventBus
from workflows.factory import create_workflow
from workflows.rag import create_rag_provider
from workflows.session_memory import create_memory_store

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


def _status_from_output(event: WorkflowEvent) -> str | None:
    status = event.payload.get("status")
    if not isinstance(status, str):
        return None
    if status in {"completed", "failed", "escalated"}:
        return status
    return None


def _sync_event_to_run(event: WorkflowEvent) -> None:
    workflow_run_repository.append_workflow_event(event.thread_id, event)

    if event.type == "workflow.stage":
        stage = event.payload.get("agent")
        if isinstance(stage, str):
            workflow_run_repository.update_current_stage(event.thread_id, stage)

    if event.type == "hitl.request":
        workflow_run_repository.add_pending_approval(event.thread_id, event.payload)
        workflow_run_repository.update_workflow_status(event.thread_id, "waiting_approval")
        return

    if event.type == "hitl.response":
        checkpoint_id = event.payload.get("checkpoint_id")
        decision = event.payload.get("decision")
        reviewer = event.payload.get("reviewer")
        comments = event.payload.get("comments")
        if isinstance(checkpoint_id, str) and isinstance(decision, str):
            workflow_run_repository.resolve_approval(
                thread_id=event.thread_id,
                checkpoint_id=checkpoint_id,
                decision=decision,
                comment=comments if isinstance(comments, str) else None,
                reviewer=reviewer if isinstance(reviewer, str) else None,
            )
        workflow_run_repository.update_workflow_status(event.thread_id, "running")
        return

    if event.type == "workflow.output":
        workflow_run_repository.update_latest_output(event.thread_id, event.payload)
        output_status = _status_from_output(event)
        if output_status:
            workflow_run_repository.update_workflow_status(event.thread_id, output_status)
        else:
            workflow_run_repository.update_workflow_status(event.thread_id, "completed")
        return

    if event.type == "workflow.failed":
        workflow_run_repository.update_workflow_status(event.thread_id, "failed")


event_bus.add_listener(_sync_event_to_run)
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
