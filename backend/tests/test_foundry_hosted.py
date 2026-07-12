from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
os.environ.setdefault("OTEL_LOGS_EXPORTER", "none")
os.environ.setdefault("FOUNDRY_HOSTED_SKIP_APP_INIT_FOR_TESTS", "true")

from foundry import main as foundry_main


class _FakeTextResponse:
    def __init__(self, context: object, request: object, *, text: str) -> None:
        self.context = context
        self.request = request
        self.text = text


class _FakeRepository:
    def __init__(self) -> None:
        self.details_by_thread: dict[str, object] = {}

    def get_workflow_run(self, thread_id: str) -> object | None:
        return self.details_by_thread.get(thread_id)


class _FakeService:
    def __init__(self) -> None:
        self.started: list[dict[str, str]] = []
        self.resumed: list[dict[str, str]] = []

    async def start_chat_run(self, request: object) -> object:
        self.started.append(
            {
                "thread_id": request.thread_id,  # type: ignore[attr-defined]
                "session_id": request.session_id,  # type: ignore[attr-defined]
                "message": request.message,  # type: ignore[attr-defined]
            }
        )
        return SimpleNamespace(run_id="run-1", thread_id=request.thread_id)

    async def respond_hitl(self, request: object) -> object:
        self.resumed.append(
            {
                "checkpoint_id": request.checkpoint_id,  # type: ignore[attr-defined]
                "decision": request.decision,  # type: ignore[attr-defined]
            }
        )
        return SimpleNamespace(accepted=True, checkpoint_id=request.checkpoint_id, thread_id="c1")


def _details(
    *,
    thread_id: str,
    status: str,
    pending: list[dict[str, str]] | None = None,
    output_message: str = "",
) -> object:
    events = [
        SimpleNamespace(
            model_dump=lambda: {
                "id": "evt-1",
                "type": "workflow.stage",
                "thread_id": thread_id,
                "payload": {"agent": "triage", "status": "completed"},
            }
        ),
        SimpleNamespace(
            model_dump=lambda: {
                "id": "evt-2",
                "type": "tool.call",
                "thread_id": thread_id,
                "payload": {"local_tool": "fetch_order_status/fetch_policy"},
            }
        ),
    ]
    pending_models = [
        SimpleNamespace(
            status=item["status"], checkpoint_id=item["checkpoint_id"], model_dump=lambda i=item: i
        )
        for item in (pending or [])
    ]
    latest_output = {"message": output_message} if output_message else None
    return SimpleNamespace(
        thread_id=thread_id,
        status=status,
        events=events,
        pending_approvals=pending_models,
        latest_output=latest_output,
    )


def test_parse_input_extracts_conversation_and_message() -> None:
    parsed = foundry_main._parse_input(
        {
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Resolve delayed order ORD-1001"}],
                }
            ],
            "conversation_id": "C1",
        },
        None,
    )
    assert parsed.conversation_id == "C1"
    assert parsed.message == "Resolve delayed order ORD-1001"
    assert parsed.decision is None
    assert parsed.checkpoint_id is None


def test_parse_input_detects_function_call_output_decision() -> None:
    parsed = foundry_main._parse_input(
        {
            "conversation_id": "C1",
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "cp-123",
                    "output": {"decision": "approve"},
                }
            ],
        },
        None,
    )
    assert parsed.decision == "approve"
    assert parsed.checkpoint_id == "cp-123"


def test_parse_input_resume_hitl_without_decision_does_not_auto_approve() -> None:
    parsed = foundry_main._parse_input(
        {"conversation_id": "C1", "metadata": {"operation": "resume_hitl"}},
        None,
    )
    assert parsed.decision is None


@pytest.mark.asyncio
async def test_run_from_responses_starts_workflow_and_returns_serialized_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _FakeRepository()
    service = _FakeService()
    repo.details_by_thread["C1"] = _details(
        thread_id="C1",
        status="completed",
        output_message="Resolution complete. Action 'issue_partial_refund' submitted for order ord-1001.",
    )
    monkeypatch.setattr(foundry_main, "workflow_run_repository", repo)
    monkeypatch.setattr(foundry_main, "order_resolution_service", service)

    response = await foundry_main._run_from_responses(
        {"conversation_id": "C1", "input": "Resolve delayed order ORD-1001"},
        None,
        _FakeTextResponse,
    )

    payload = json.loads(response.text)
    assert service.started == [
        {
            "thread_id": "C1",
            "session_id": "C1",
            "message": "Resolve delayed order ORD-1001",
        }
    ]
    assert payload["thread_id"] == "C1"
    assert payload["status"] == "completed"
    assert any(event["type"] == "tool.call" for event in payload["events"])


@pytest.mark.asyncio
async def test_run_from_responses_resumes_pending_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _FakeRepository()
    service = _FakeService()
    repo.details_by_thread["C1"] = _details(
        thread_id="C1",
        status="waiting_approval",
        pending=[{"checkpoint_id": "cp-123", "status": "pending"}],
    )
    monkeypatch.setattr(foundry_main, "workflow_run_repository", repo)
    monkeypatch.setattr(foundry_main, "order_resolution_service", service)

    await foundry_main._run_from_responses(
        {
            "conversation_id": "C1",
            "input": [{"type": "function_call_output", "call_id": "cp-123", "output": "approve"}],
        },
        None,
        _FakeTextResponse,
    )

    assert service.resumed == [{"checkpoint_id": "cp-123", "decision": "approve"}]
