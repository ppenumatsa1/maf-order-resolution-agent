from __future__ import annotations

from uuid import uuid4

from app.infrastructure.persistence import CheckpointStore, WorkflowRunRepository
from app.infrastructure.persistence.session_memory import SessionMemoryStore
from app.modules.order_resolution.models import WorkflowEvent


def test_persists_and_reloads_after_store_reinit() -> None:
    thread_id = str(uuid4())

    run_repo = WorkflowRunRepository()
    memory_store = SessionMemoryStore()
    checkpoint_store = CheckpointStore()

    run_repo.create_workflow_run(thread_id=thread_id, input_text="Order ORD-1009 delayed")
    memory_store.append_message(thread_id, "user", "Order ORD-1009 delayed")
    memory_store.append_message(thread_id, "assistant", "Investigating your order now")

    event = WorkflowEvent(
        type="workflow.stage",
        thread_id=thread_id,
        payload={"agent": "triage", "status": "completed"},
    )
    run_repo.append_workflow_event(thread_id, event)

    checkpoint = checkpoint_store.create(
        thread_id=thread_id,
        state={"run_id": str(uuid4()), "resolution": {"requires_hitl": True}},
    )
    checkpoint["status"] = "approved"
    checkpoint["reviewer"] = "demo-reviewer"
    checkpoint_store.update(checkpoint)

    # Simulate process restart by constructing fresh store/repository instances.
    reloaded_repo = WorkflowRunRepository()
    reloaded_memory = SessionMemoryStore()
    reloaded_checkpoint_store = CheckpointStore()

    reloaded_run = reloaded_repo.get_workflow_run(thread_id)
    assert reloaded_run is not None
    assert reloaded_run.thread_id == thread_id
    assert any(item.id == event.id for item in reloaded_run.events)

    reloaded_messages = reloaded_memory.get_messages(thread_id)
    assert len(reloaded_messages) == 2
    assert reloaded_messages[0]["role"] == "user"
    assert reloaded_messages[1]["role"] == "assistant"

    reloaded_checkpoint = reloaded_checkpoint_store.get(checkpoint["checkpoint_id"])
    assert reloaded_checkpoint is not None
    assert reloaded_checkpoint["status"] == "approved"
    assert reloaded_checkpoint["reviewer"] == "demo-reviewer"
