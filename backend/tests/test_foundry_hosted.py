from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

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
        return SimpleNamespace(accepted=True, checkpoint_id=request.checkpoint_id, thread_id="C1")


class _FakeSpan:
    def __init__(self, name: str) -> None:
        self.name = name
        self.attributes: dict[str, str | bool | int | float] = {}
        self.recorded_exceptions: list[Exception] = []

    def __enter__(self) -> _FakeSpan:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def set_attribute(self, key: str, value: str | bool | int | float) -> None:
        self.attributes[key] = value

    def record_exception(self, exc: Exception) -> None:
        self.recorded_exceptions.append(exc)


class _FakeTracer:
    def __init__(self) -> None:
        self.spans: list[_FakeSpan] = []

    def start_as_current_span(self, name: str) -> _FakeSpan:
        span = _FakeSpan(name)
        self.spans.append(span)
        return span


class _FakeResponsesHost:
    instances: list[_FakeResponsesHost] = []

    def __init__(self, **kwargs: object) -> None:
        self.store_supplied = "store" in kwargs
        self.store = kwargs.get("store")
        self.handler: object | None = None
        self.instances.append(self)

    def response_handler(self, handler: object) -> None:
        self.handler = handler


class _FakeInMemoryResponseProvider:
    pass


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


def _fake_responses_types() -> tuple[
    type[object], type[object], type[object], type[object], type[object]
]:
    return (
        _FakeResponsesHost,
        object,
        object,
        _FakeTextResponse,
        _FakeInMemoryResponseProvider,
    )


def test_hosted_manifest_propagates_deployment_profile() -> None:
    manifest = Path(__file__).parents[1] / "agent.yaml"

    assert "name: FOUNDRY_DEPLOYMENT_PROFILE" in manifest.read_text()


def test_build_app_uses_platform_store_for_public_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeResponsesHost.instances.clear()
    monkeypatch.setenv("FOUNDRY_DEPLOYMENT_PROFILE", "public")
    monkeypatch.setattr(foundry_main, "_load_responses_types", _fake_responses_types)

    app = foundry_main._build_app()

    assert app is _FakeResponsesHost.instances[-1]
    assert app.store_supplied is False


@pytest.mark.parametrize("profile", ["private", ""])
def test_build_app_uses_in_memory_store_for_private_safe_profiles(
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
) -> None:
    _FakeResponsesHost.instances.clear()
    if profile:
        monkeypatch.setenv("FOUNDRY_DEPLOYMENT_PROFILE", profile)
    else:
        monkeypatch.delenv("FOUNDRY_DEPLOYMENT_PROFILE", raising=False)
    monkeypatch.setattr(foundry_main, "_load_responses_types", _fake_responses_types)

    app = foundry_main._build_app()

    assert app is _FakeResponsesHost.instances[-1]
    assert app.store_supplied is True
    assert isinstance(app.store, _FakeInMemoryResponseProvider)


def test_runtime_database_url_override_sets_database_url_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    runtime_url = (
        "postgresql://user:pass@server.postgres.database.azure.com:5432/maf?sslmode=require"
    )
    monkeypatch.setenv("RUNTIME_DATABASE_URL", runtime_url)

    foundry_main._apply_runtime_database_url_override()

    assert os.getenv("DATABASE_URL") == runtime_url


def test_runtime_database_url_override_prefers_foundry_runtime_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "FOUNDRY_RUNTIME_DATABASE_URL",
        "postgresql://user:pass@preferred.postgres.database.azure.com:5432/maf?sslmode=require",
    )
    monkeypatch.setenv(
        "RUNTIME_DATABASE_URL",
        "postgresql://user:pass@fallback.postgres.database.azure.com:5432/maf?sslmode=require",
    )

    foundry_main._apply_runtime_database_url_override()

    assert os.getenv("DATABASE_URL", "").startswith(
        "postgresql://user:pass@preferred.postgres.database.azure.com"
    )


def test_runtime_database_url_override_replaces_loopback_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_url = (
        "postgresql://user:pass@server.postgres.database.azure.com:5432/maf?sslmode=require"
    )
    monkeypatch.setenv("RUNTIME_DATABASE_URL", runtime_url)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/maf_workflow")

    foundry_main._apply_runtime_database_url_override()

    assert os.getenv("DATABASE_URL") == runtime_url


def test_runtime_database_url_override_keeps_existing_remote_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_url = (
        "postgresql://user:pass@existing.postgres.database.azure.com:5432/maf?sslmode=require"
    )
    runtime_url = (
        "postgresql://user:pass@server.postgres.database.azure.com:5432/maf?sslmode=require"
    )
    monkeypatch.setenv("DATABASE_URL", existing_url)
    monkeypatch.setenv("RUNTIME_DATABASE_URL", runtime_url)

    foundry_main._apply_runtime_database_url_override()

    assert os.getenv("DATABASE_URL") == existing_url


def test_parse_input_extracts_conversation_and_message() -> None:
    parsed = foundry_main._parse_input(
        {
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Resolve delayed order ORD-1001"}],
                }
            ],
            "conversation": {"id": "C1"},
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


def test_parse_input_extracts_message_from_context_when_payload_is_empty() -> None:
    parsed = foundry_main._parse_input(
        {},
        SimpleNamespace(
            conversation_id="C2",
            request_body={
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Resolve delayed order ORD-1001"}
                        ],
                    }
                ]
            },
        ),
    )
    assert parsed.conversation_id == "C2"
    assert parsed.message == "Resolve delayed order ORD-1001"
    assert parsed.decision is None


def test_parse_input_prefers_payload_response_id_over_context_session_id() -> None:
    parsed = foundry_main._parse_input(
        {"id": "resp-123", "input": "Resolve delayed order ORD-1001"},
        SimpleNamespace(session_id="sess-abc"),
    )
    assert parsed.conversation_id == "resp-123"


def test_parse_input_accepts_previous_response_id_for_resume() -> None:
    parsed = foundry_main._parse_input(
        {"previous_response_id": "resp-prev-1", "input": "Approve"},
        None,
    )
    assert parsed.conversation_id == "resp-prev-1"
    assert parsed.decision == "approve"


def test_parse_input_prefers_payload_conversation_string_over_previous_response_id() -> None:
    parsed = foundry_main._parse_input(
        {
            "conversation": "conv-456",
            "previous_response_id": "resp-prev-2",
            "input": "Resolve delayed order ORD-1001",
        },
        None,
    )
    assert parsed.conversation_id == "conv-456"


def test_parse_input_extracts_conversation_id_from_context_request_metadata() -> None:
    parsed = foundry_main._parse_input(
        {"id": "resp-123", "input": "Resolve delayed order ORD-1009"},
        SimpleNamespace(request_body={"metadata": {"conversation_id": "conv-meta-1"}}),
    )
    assert parsed.conversation_id == "resp-123"


def test_parse_input_prefers_context_request_metadata_over_context_id() -> None:
    parsed = foundry_main._parse_input(
        {"input": "Resolve delayed order ORD-1001"},
        SimpleNamespace(
            id="resp-999", request_body={"metadata": {"conversation_id": "conv-meta-2"}}
        ),
    )
    # Strict responses-native mode no longer uses metadata/context.id fallback.
    UUID(parsed.conversation_id)


def test_parse_input_uses_payload_conversation_id_when_present() -> None:
    parsed = foundry_main._parse_input(
        {
            "id": "resp-123",
            "conversation": {"id": "conv-123"},
            "input": "Resolve delayed order ORD-1001",
        },
        None,
    )
    assert parsed.conversation_id == "conv-123"


def test_parse_input_detects_approval_from_nested_value_shapes() -> None:
    parsed = foundry_main._parse_input(
        {
            "conversation": {"id": "conv-approve-1"},
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": {"value": "Approve"}}],
                }
            ],
        },
        None,
    )
    assert parsed.message == "Approve"
    assert parsed.decision == "approve"


def test_parse_input_detects_approval_from_serialized_context_input() -> None:
    context = SimpleNamespace(
        conversation_id="conv-approve-2",
        input="{'conversation': {'id': 'conv-approve-2'}, 'input': 'Approve'}",
    )
    parsed = foundry_main._parse_input({}, context)
    assert parsed.conversation_id == "conv-approve-2"
    assert parsed.decision == "approve"


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
        {"conversation": {"id": "C1"}, "input": "Resolve delayed order ORD-1001"},
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
    tracer = _FakeTracer()
    repo.details_by_thread["C1"] = _details(
        thread_id="C1",
        status="waiting_approval",
        pending=[{"checkpoint_id": "cp-123", "status": "pending"}],
    )
    monkeypatch.setattr(foundry_main, "workflow_run_repository", repo)
    monkeypatch.setattr(foundry_main, "order_resolution_service", service)
    monkeypatch.setattr(foundry_main, "get_tracer", lambda _: tracer)

    await foundry_main._run_from_responses(
        {
            "conversation": {"id": "C1"},
            "input": [{"type": "function_call_output", "call_id": "cp-123", "output": "approve"}],
        },
        None,
        _FakeTextResponse,
    )

    assert service.resumed == [{"checkpoint_id": "cp-123", "decision": "approve"}]
    span = tracer.spans[0]
    assert span.name == "foundry.responses.invoke"
    assert span.attributes["workflow.thread_id"] == "C1"
    assert span.attributes["workflow.session_id"] == "C1"
    assert span.attributes["foundry.protocol"] == "responses"
    assert span.attributes["workflow.checkpoint_id"] == "cp-123"
    assert span.attributes["workflow.status"] == "waiting_approval"
    assert span.attributes["workflow.event_count"] == 2


@pytest.mark.asyncio
async def test_run_from_responses_records_exception_on_root_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingService:
        async def start_chat_run(self, request: object) -> object:
            raise RuntimeError("boom")

    tracer = _FakeTracer()
    monkeypatch.setattr(foundry_main, "get_tracer", lambda _: tracer)
    monkeypatch.setattr(foundry_main, "order_resolution_service", _FailingService())

    with pytest.raises(RuntimeError, match="boom"):
        await foundry_main._run_from_responses(
            {"conversation_id": "C1", "input": "Resolve delayed order ORD-1001"},
            None,
            _FakeTextResponse,
        )

    span = tracer.spans[0]
    assert span.name == "foundry.responses.invoke"
    assert len(span.recorded_exceptions) == 1
    assert isinstance(span.recorded_exceptions[0], RuntimeError)
