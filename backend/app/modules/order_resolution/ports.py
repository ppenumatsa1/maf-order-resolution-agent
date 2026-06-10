from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from app.modules.order_resolution.models import WorkflowContext, WorkflowEvent


class EventPublisher(Protocol):
    async def publish(self, event: WorkflowEvent) -> None: ...


class WorkflowEngine(Protocol):
    async def start(self, context: WorkflowContext) -> None: ...

    async def handle_hitl_response(
        self,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> str: ...


class CheckpointRepository(Protocol):
    def create(self, thread_id: str, state: dict[str, Any]) -> dict[str, Any]: ...

    def get(self, checkpoint_id: str) -> dict[str, Any] | None: ...

    def try_resolve(
        self,
        *,
        checkpoint_id: str,
        resolved_status: str,
        reviewer: str,
        comments: str | None,
    ) -> bool: ...


class SessionMemoryRepository(Protocol):
    def get_messages(self, thread_id: str) -> list[dict[str, Any]]: ...

    def append_message(self, thread_id: str, role: str, content: str) -> None: ...

    def summarize_context(self, thread_id: str, max_messages: int = 8) -> str: ...


class IdempotencyRepository(Protocol):
    def execute_once(
        self,
        *,
        workflow_run_id: str,
        step_name: str,
        business_id: str,
        operation: Callable[[], str],
    ) -> tuple[str, bool]: ...


class McpKnowledgePort(Protocol):
    async def search(self, query: str) -> dict[str, Any]: ...


class WorkflowRunRepositoryPort(Protocol):
    def create_workflow_run(
        self,
        thread_id: str,
        input_text: str,
        session_id: str | None = None,
        customer_id: str | None = None,
    ) -> dict[str, Any] | None: ...

    def append_workflow_event(self, thread_id: str, event: WorkflowEvent) -> None: ...

    def update_current_stage(self, thread_id: str, stage: str | None) -> None: ...

    def add_pending_approval(self, thread_id: str, approval: dict[str, Any]) -> None: ...

    def update_workflow_status(self, thread_id: str, status: str) -> None: ...

    def resolve_approval(
        self,
        thread_id: str,
        checkpoint_id: str,
        decision: str,
        comment: str | None,
        reviewer: str | None,
    ) -> None: ...

    def update_latest_output(self, thread_id: str, output: dict[str, Any]) -> None: ...
