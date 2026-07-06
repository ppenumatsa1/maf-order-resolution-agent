from __future__ import annotations

import json
import os
from decimal import Decimal
from uuid import uuid4

os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
os.environ.setdefault("OTEL_LOGS_EXPORTER", "none")
os.environ.setdefault("FOUNDRY_HOSTED_SKIP_APP_INIT_FOR_TESTS", "true")

import pytest
from app.foundry import client as foundry_client_module
from app.foundry.client import FoundryHostedClient
from app.foundry.config import get_foundry_hosted_config
from app.foundry.models import FoundryEventPayload, FoundryInvocationResponse
from app.foundry.workflow import FoundryHostedWorkflow
from app.infrastructure.events import EventBus
from app.main import app
from app.modules.order_resolution.models import WorkflowContext
from fastapi.testclient import TestClient
from foundry import main as foundry_main_module
from foundry import memory_store as memory_store_module
from foundry.conversation_shadow import (
    CONVERSATION_SHADOW_RESPONSES,
    FoundryResponsesConversationShadowClient,
    HostedConversationShadowConfig,
    get_hosted_conversation_shadow_config,
)
from foundry.main import (
    _coerce_response_payload,
    _create_hosted_app,
    _handle_response_payload,
    _parse_invocation_payload,
    get_hosted_protocol,
    responses_protocol_blocker,
)
from foundry.memory_store import (
    FoundryMemoryStoreClient,
    HostedMemoryConfig,
    get_hosted_memory_config,
)
from foundry.state_store import (
    HostedCheckpointState,
    build_hosted_state_store,
)


def test_foundry_config_requires_invocations_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOUNDRY_HOSTED_INVOCATIONS_URL", raising=False)
    with pytest.raises(ValueError, match="FOUNDRY_HOSTED_INVOCATIONS_URL"):
        get_foundry_hosted_config(required=True)


@pytest.mark.asyncio
async def test_foundry_workflow_publishes_response_events() -> None:
    thread_id = str(uuid4())
    expected_thread_id = thread_id
    event_bus = EventBus()
    response = FoundryInvocationResponse(
        thread_id=thread_id,
        events=[
            FoundryEventPayload(
                type="workflow.stage",
                thread_id=thread_id,
                payload={"agent": "triage", "status": "completed"},
            ),
            FoundryEventPayload(
                type="workflow.output",
                thread_id=thread_id,
                payload={"status": "completed"},
            ),
        ],
    )

    class DummyClient:
        async def start_workflow(self, context: WorkflowContext) -> FoundryInvocationResponse:
            assert context.thread_id == thread_id
            return response

        async def resume_hitl(
            self,
            *,
            checkpoint_id: str,
            decision: str,
            reviewer: str,
            comments: str | None,
            thread_id: str | None = None,
            action: str | None = None,
            order_id: str | None = None,
            amount: float | int | None = None,
        ) -> FoundryInvocationResponse:
            return FoundryInvocationResponse(
                thread_id=thread_id or expected_thread_id,
                events=[
                    FoundryEventPayload(
                        type="hitl.response",
                        thread_id=thread_id or expected_thread_id,
                        payload={"checkpoint_id": checkpoint_id, "decision": decision},
                    )
                ],
            )

    workflow = FoundryHostedWorkflow(event_bus=event_bus, client=DummyClient())
    await workflow.start(
        WorkflowContext(
            run_id=str(uuid4()),
            thread_id=thread_id,
            session_id=thread_id,
            customer_id="cust-test",
            user_message="Order ORD-1001 late",
        )
    )

    history = event_bus.history_as_json(thread_id)
    assert "workflow.stage" in history
    assert "workflow.output" in history

    resumed_thread = await workflow.handle_hitl_response(
        checkpoint_id="cp-1",
        decision="approve",
        reviewer="reviewer-1",
        comments=None,
    )
    assert resumed_thread == thread_id
    resumed_history = event_bus.history_as_json(thread_id)
    assert "hitl.response" in resumed_history


@pytest.mark.asyncio
async def test_foundry_workflow_remaps_hosted_thread_to_canonical_thread() -> None:
    canonical_thread_id = str(uuid4())
    hosted_thread_id = str(uuid4())
    event_bus = EventBus()
    response = FoundryInvocationResponse(
        thread_id=hosted_thread_id,
        events=[
            FoundryEventPayload(
                type="workflow.output",
                payload={"status": "completed"},
            )
        ],
    )

    class DummyClient:
        async def start_workflow(self, context: WorkflowContext) -> FoundryInvocationResponse:
            assert context.thread_id == canonical_thread_id
            return response

        async def resume_hitl(
            self,
            *,
            checkpoint_id: str,
            decision: str,
            reviewer: str,
            comments: str | None,
            thread_id: str | None = None,
            action: str | None = None,
            order_id: str | None = None,
            amount: float | int | None = None,
        ) -> FoundryInvocationResponse:
            return FoundryInvocationResponse(
                thread_id=hosted_thread_id,
                events=[
                    FoundryEventPayload(
                        type="hitl.response",
                        thread_id=hosted_thread_id,
                        payload={"checkpoint_id": checkpoint_id, "decision": decision},
                    )
                ],
            )

    workflow = FoundryHostedWorkflow(event_bus=event_bus, client=DummyClient())
    await workflow.start(
        WorkflowContext(
            run_id=str(uuid4()),
            thread_id=canonical_thread_id,
            session_id=canonical_thread_id,
            customer_id="cust-test",
            user_message="Order ORD-1001 late",
        )
    )

    canonical_history = event_bus.history_as_json(canonical_thread_id)
    assert "foundry_invocations" in canonical_history
    assert "tool.call" in canonical_history
    assert "workflow.output" in canonical_history

    resumed_thread = await workflow.handle_hitl_response(
        checkpoint_id="cp-1",
        decision="approve",
        reviewer="reviewer-1",
        comments=None,
    )
    assert resumed_thread == canonical_thread_id
    resumed_history = event_bus.history_as_json(canonical_thread_id)
    assert "foundry_invocations" in resumed_history
    assert "hitl.response" in resumed_history


@pytest.mark.asyncio
async def test_foundry_resume_uses_repository_approval_context() -> None:
    thread_id = str(uuid4())
    hosted_thread_id = str(uuid4())
    event_bus = EventBus()
    observed: dict[str, object] = {}

    class DummyRepository:
        def get_pending_approval_context(self, checkpoint_id: str) -> dict[str, object] | None:
            assert checkpoint_id == "cp-ctx"
            return {
                "thread_id": thread_id,
                "action": "offer_credit",
                "order_id": "ord-1009",
                "amount": Decimal("185.0"),
                "status": "pending",
            }

    class DummyClient:
        async def start_workflow(self, context: WorkflowContext) -> FoundryInvocationResponse:
            return FoundryInvocationResponse(thread_id=hosted_thread_id, events=[])

        async def resume_hitl(
            self,
            *,
            checkpoint_id: str,
            decision: str,
            reviewer: str,
            comments: str | None,
            thread_id: str | None = None,
            action: str | None = None,
            order_id: str | None = None,
            amount: float | int | None = None,
        ) -> FoundryInvocationResponse:
            observed.update(
                {
                    "checkpoint_id": checkpoint_id,
                    "thread_id": thread_id,
                    "action": action,
                    "order_id": order_id,
                    "amount": amount,
                }
            )
            return FoundryInvocationResponse(
                thread_id=hosted_thread_id,
                events=[
                    FoundryEventPayload(
                        type="hitl.response",
                        thread_id=hosted_thread_id,
                        payload={"checkpoint_id": checkpoint_id, "decision": decision},
                    )
                ],
            )

    workflow = FoundryHostedWorkflow(
        event_bus=event_bus,
        client=DummyClient(),
        workflow_run_repository=DummyRepository(),
    )
    await workflow.start(
        WorkflowContext(
            run_id=str(uuid4()),
            thread_id=thread_id,
            session_id=thread_id,
            customer_id="cust-test",
            user_message="Order ORD-1009 delayed",
        )
    )

    resumed_thread = await workflow.handle_hitl_response(
        checkpoint_id="cp-ctx",
        decision="approve",
        reviewer="reviewer-1",
        comments=None,
    )
    assert resumed_thread == thread_id
    assert observed == {
        "checkpoint_id": "cp-ctx",
        "thread_id": thread_id,
        "action": "offer_credit",
        "order_id": "ord-1009",
        "amount": 185.0,
    }


@pytest.mark.asyncio
async def test_foundry_workflow_emits_failure_event_on_invocation_error() -> None:
    thread_id = str(uuid4())
    event_bus = EventBus()

    class FailingClient:
        async def start_workflow(self, context: WorkflowContext) -> FoundryInvocationResponse:
            raise RuntimeError("downstream unavailable")

        async def resume_hitl(
            self,
            *,
            checkpoint_id: str,
            decision: str,
            reviewer: str,
            comments: str | None,
            thread_id: str | None = None,
            action: str | None = None,
            order_id: str | None = None,
            amount: float | int | None = None,
        ) -> FoundryInvocationResponse:
            raise AssertionError("resume is not called in this test")

    workflow = FoundryHostedWorkflow(event_bus=event_bus, client=FailingClient())
    with pytest.raises(RuntimeError, match="downstream unavailable"):
        await workflow.start(
            WorkflowContext(
                run_id=str(uuid4()),
                thread_id=thread_id,
                session_id=thread_id,
                customer_id="cust-test",
                user_message="Order ORD-1009 delayed",
            )
        )

    history = event_bus.history_as_json(thread_id)
    assert "workflow.failed" in history


def test_foundry_event_ingress_requires_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOW_MODE", "foundry_hosted")
    monkeypatch.setenv("FOUNDRY_EVENT_CALLBACK_TOKEN", "secret-token")
    client = TestClient(app)
    run = client.post(
        "/api/chat/run",
        json={"message": "Order ORD-1001 arrived late."},
    )
    assert run.status_code == 200
    thread_id = run.json()["thread_id"]
    payload = {
        "events": [
            {
                "type": "workflow.stage",
                "thread_id": thread_id,
                "payload": {"agent": "triage", "status": "started"},
            }
        ]
    }
    unauthorized = client.post("/api/foundry/events", json=payload)
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/api/foundry/events",
        headers={"x-foundry-callback-token": "secret-token"},
        json=payload,
    )
    assert authorized.status_code == 200
    assert authorized.json() == {"accepted": 1}


def test_foundry_invoke_proxy_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOUNDRY_HOSTED_INVOCATIONS_URL", "https://example.test/invocations")
    client = TestClient(app)

    async def fake_invoke_raw(
        self: FoundryHostedClient, payload: dict[str, object]
    ) -> dict[str, object]:
        assert payload == {"message": "hello from ui"}
        return {"thread_id": "thread-1", "status": "completed", "echo": payload["message"]}

    monkeypatch.setattr(FoundryHostedClient, "invoke_raw", fake_invoke_raw)

    response = client.post(
        "/api/foundry/invoke",
        json={"payload": {"message": "hello from ui"}},
    )
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "response": {
            "thread_id": "thread-1",
            "status": "completed",
            "echo": "hello from ui",
        },
    }


def test_foundry_invoke_proxy_requires_env_invocations_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOUNDRY_HOSTED_INVOCATIONS_URL", raising=False)
    client = TestClient(app)
    response = client.post("/api/foundry/invoke", json={"payload": {"message": "hello"}})
    assert response.status_code == 503
    assert "FOUNDRY_HOSTED_INVOCATIONS_URL is not configured" in response.json()["detail"]


def test_foundry_jwt_detection() -> None:
    assert foundry_client_module._looks_like_jwt("a.b.c")
    assert not foundry_client_module._looks_like_jwt("abc")
    assert not foundry_client_module._looks_like_jwt("a..c")


def test_foundry_hosted_parser_accepts_json_string_resume_payload() -> None:
    resume_payload = {
        "operation": "resume_hitl",
        "checkpoint_id": "cp-1",
        "decision": "approve",
        "thread_id": "thread-1",
        "order_id": "ord-1009",
        "action": "offer_credit",
        "amount": 185.0,
    }

    parsed = _parse_invocation_payload(json.dumps(json.dumps(resume_payload)).encode())

    assert parsed == resume_payload


def test_foundry_hosted_parser_accepts_nested_json_string_resume_payload() -> None:
    resume_payload = {
        "operation": "resume_hitl",
        "checkpoint_id": "cp-1",
        "decision": "reject",
        "thread_id": "thread-1",
        "order_id": "ord-1009",
        "action": "offer_credit",
    }

    parsed = _parse_invocation_payload(json.dumps({"input": json.dumps(resume_payload)}).encode())

    assert parsed == resume_payload


def test_foundry_hosted_protocol_defaults_to_invocations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOUNDRY_HOSTED_PROTOCOL", raising=False)

    assert get_hosted_protocol() == "dual"


def test_foundry_hosted_protocol_accepts_dual_and_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOUNDRY_HOSTED_PROTOCOL", "dual")
    assert get_hosted_protocol() == "dual"

    monkeypatch.setenv("FOUNDRY_HOSTED_PROTOCOL", "responses")
    assert get_hosted_protocol() == "responses"


def test_foundry_hosted_protocol_rejects_unknown_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOUNDRY_HOSTED_PROTOCOL", "other")

    with pytest.raises(ValueError, match="FOUNDRY_HOSTED_PROTOCOL"):
        get_hosted_protocol()


def test_foundry_responses_protocol_reports_missing_optional_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(foundry_main_module, "_load_responses_protocol_types", lambda: None)
    blocker = responses_protocol_blocker()

    assert blocker is not None
    assert "azure-ai-agentserver-responses" in blocker


def test_foundry_dual_protocol_requires_responses_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(foundry_main_module, "_load_responses_protocol_types", lambda: None)

    with pytest.raises(RuntimeError, match="azure-ai-agentserver-responses"):
        _create_hosted_app("dual")


def test_foundry_responses_payload_coerces_nested_input_text() -> None:
    payload = _coerce_response_payload(
        {
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Order ORD-1001 is late"}],
                }
            ],
            "thread_id": "thread-1",
        }
    )

    assert payload["message"] == "Order ORD-1001 is late"


@pytest.mark.asyncio
async def test_foundry_response_handler_returns_invocation_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOUNDRY_HOSTED_MEMORY_PROVIDER", "none")

    class FakeTextResponse:
        def __init__(self, context: object, request: object, *, text: str) -> None:
            self.context = context
            self.request = request
            self.text = text

    response = await _handle_response_payload(
        {
            "input": "Order ORD-1001 arrived late",
            "thread_id": "thread-responses",
        },
        None,
        FakeTextResponse,
    )

    body = json.loads(response.text)
    assert body["thread_id"] == "thread-responses"
    assert body["status"] == "completed"
    assert [event["type"] for event in body["events"]][-1] == "workflow.output"


@pytest.mark.asyncio
async def test_foundry_response_shadow_operation_records_without_workflow_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOUNDRY_HOSTED_MEMORY_PROVIDER", "none")
    monkeypatch.setenv("FOUNDRY_HOSTED_CONVERSATION_SHADOW_PROVIDER", "none")

    class FakeTextResponse:
        def __init__(self, context: object, request: object, *, text: str) -> None:
            self.text = text

    response = await _handle_response_payload(
        {
            "input": "Order ORD-1001 arrived late",
            "metadata": {
                "operation": "shadow_conversation",
                "thread_id": "thread-shadow",
            },
        },
        None,
        FakeTextResponse,
    )

    body = json.loads(response.text)
    assert body == {"thread_id": "thread-shadow", "status": "shadow_recorded", "events": []}


@pytest.mark.asyncio
async def test_foundry_invocation_shadows_conversation_to_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOUNDRY_HOSTED_MEMORY_PROVIDER", "none")
    monkeypatch.setenv("FOUNDRY_HOSTED_CONVERSATION_SHADOW_PROVIDER", "none")
    observed: list[dict[str, object]] = []

    class FakeShadowClient:
        async def append_conversation_item(
            self,
            *,
            thread_id: str,
            role: str,
            content: str,
            source_operation: str,
        ) -> bool:
            observed.append(
                {
                    "thread_id": thread_id,
                    "role": role,
                    "content": content,
                    "source_operation": source_operation,
                }
            )
            return True

    monkeypatch.setattr(foundry_main_module, "_CONVERSATION_SHADOW_CLIENT", FakeShadowClient())

    class RequestContext:
        state = type("State", (), {"session_id": "thread-shadow"})()

    response = await foundry_main_module._handle_invocation_payload(
        RequestContext(),
        {"message": "Order ORD-1001 arrived late", "thread_id": "thread-shadow"},
        "start_workflow",
    )

    assert response.status_code == 200
    assert observed == [
        {
            "thread_id": "thread-shadow",
            "role": "user",
            "content": "Order ORD-1001 arrived late",
            "source_operation": "start_workflow",
        }
    ]


def test_foundry_conversation_shadow_config_derives_responses_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOUNDRY_HOSTED_CONVERSATION_SHADOW_PROVIDER", "responses")
    monkeypatch.setenv(
        "FOUNDRY_HOSTED_INVOCATIONS_URL",
        "https://example.test/agent/invocations",
    )

    config = get_hosted_conversation_shadow_config()

    assert config.provider == CONVERSATION_SHADOW_RESPONSES
    assert config.responses_url == "https://example.test/agent/responses"


@pytest.mark.asyncio
async def test_foundry_conversation_shadow_client_posts_synthetic_metadata() -> None:
    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

    class FakeHttpClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        async def post(
            self,
            url: str,
            *,
            json: dict[str, object],
            headers: dict[str, str],
        ) -> FakeResponse:
            self.requests.append({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    http_client = FakeHttpClient()
    client = FoundryResponsesConversationShadowClient(
        HostedConversationShadowConfig(
            provider="responses",
            responses_url="https://example.test/responses",
            api_key="test-key",
            timeout_seconds=3.0,
        ),
        http_client=http_client,  # type: ignore[arg-type]
    )

    assert (
        await client.append_conversation_item(
            thread_id="thread-1",
            role="user",
            content="Order ORD-1009 is delayed",
            source_operation="start_workflow",
        )
        is True
    )
    request = http_client.requests[0]
    assert request["url"] == "https://example.test/responses"
    payload = request["json"]
    assert isinstance(payload, dict)
    assert payload["metadata"] == {
        "operation": "shadow_conversation",
        "thread_id": "thread-1",
        "source_operation": "start_workflow",
        "source_protocol": "invocations",
        "synthetic": "true",
    }


def test_foundry_hosted_state_provider_defaults_to_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOUNDRY_HOSTED_STATE_PROVIDER", raising=False)
    checkpoints: dict[str, dict[str, object]] = {}
    store = build_hosted_state_store(checkpoints)

    store.save_checkpoint(
        HostedCheckpointState(
            checkpoint_id="cp-1",
            thread_id="thread-1",
            order_id="ord-1009",
            action="offer_credit",
            amount=185.0,
        )
    )

    checkpoint = store.get_checkpoint("cp-1")
    assert checkpoint is not None
    assert checkpoint.thread_id == "thread-1"
    assert checkpoint.order_id == "ord-1009"
    assert checkpoint.action == "offer_credit"
    assert checkpoints["cp-1"]["thread_id"] == "thread-1"
    assert checkpoints["cp-1"]["status"] == "pending"
    assert "requested_at" in checkpoints["cp-1"]


def test_foundry_hosted_checkpoint_resolution_is_audited_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOUNDRY_HOSTED_STATE_PROVIDER", raising=False)
    checkpoints: dict[str, dict[str, object]] = {}
    store = build_hosted_state_store(checkpoints)
    store.save_checkpoint(
        HostedCheckpointState(
            checkpoint_id="cp-1",
            thread_id="thread-1",
            order_id="ord-1009",
            action="offer_credit",
            amount=185.0,
            telemetry_trace_context={"traceparent": "00-abc-def-01"},
        )
    )

    resolved = store.resolve_checkpoint(
        checkpoint_id="cp-1",
        decision="approve",
        reviewer="reviewer-1",
        comments="approved",
    )
    duplicate = store.resolve_checkpoint(
        checkpoint_id="cp-1",
        decision="reject",
        reviewer="reviewer-2",
        comments="late duplicate",
    )

    assert resolved is not None
    assert duplicate is not None
    assert resolved.status == "approved"
    assert duplicate.status == "approved"
    assert duplicate.reviewer == "reviewer-1"
    assert duplicate.comments == "approved"
    assert checkpoints["cp-1"]["decision"] == "approve"
    assert checkpoints["cp-1"]["reviewer"] == "reviewer-1"
    assert checkpoints["cp-1"]["comments"] == "approved"
    assert checkpoints["cp-1"]["telemetry_trace_context"] == {"traceparent": "00-abc-def-01"}


def test_foundry_hosted_state_provider_rejects_native_without_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOUNDRY_HOSTED_STATE_PROVIDER", "foundry_native")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.test/api/projects/demo")

    with pytest.raises(RuntimeError, match="durable Foundry checkpoint/state API"):
        build_hosted_state_store({})


def test_foundry_hosted_memory_config_supports_model_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOUNDRY_HOSTED_MEMORY_PROVIDER", "foundry")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.test/api/projects/demo")
    monkeypatch.setenv("FOUNDRY_HOSTED_MEMORY_STORE_NAME", "order-resolution-memory")
    monkeypatch.setenv("FOUNDRY_HOSTED_MEMORY_MODEL_DEPLOYMENT_NAME", "gpt-memory")
    monkeypatch.setenv(
        "FOUNDRY_HOSTED_MEMORY_EMBEDDINGS_DEPLOYMENT_NAME",
        "text-embedding-memory",
    )
    monkeypatch.setenv("FOUNDRY_HOSTED_MEMORY_UPDATE_DELAY_SECONDS", "15")

    config = get_hosted_memory_config()

    assert config.provider == "foundry"
    assert config.memory_store_name == "order-resolution-memory"
    assert config.chat_model == "gpt-memory"
    assert config.embedding_model == "text-embedding-memory"
    assert config.update_delay_seconds == 15


def test_foundry_memory_store_client_updates_existing_store() -> None:
    class MemoryStores:
        def __init__(self) -> None:
            self.created: list[dict[str, object]] = []
            self.updates: list[dict[str, object]] = []

        def get(self, name: str) -> object:
            assert name == "order-resolution-memory"
            return object()

        def create(self, **kwargs: object) -> None:
            self.created.append(kwargs)

        def begin_update_memories(self, **kwargs: object) -> None:
            self.updates.append(kwargs)

    class ProjectClient:
        def __init__(self) -> None:
            self.beta = type("Beta", (), {"memory_stores": MemoryStores()})()

    project_client = ProjectClient()
    client = FoundryMemoryStoreClient(
        HostedMemoryConfig(
            provider="foundry",
            project_endpoint="https://example.test/api/projects/demo",
            memory_store_name="order-resolution-memory",
            chat_model="gpt-memory",
            embedding_model="text-embedding-memory",
            update_delay_seconds=15,
        ),
        project_client=project_client,
    )

    updated = client.append_conversation_item(
        thread_id="thread-1",
        role="user",
        content="Order ORD-1009 is delayed",
    )

    memory_stores = project_client.beta.memory_stores
    assert updated is True
    assert memory_stores.created == []
    assert memory_stores.updates == [
        {
            "name": "order-resolution-memory",
            "scope": "thread-1",
            "items": [
                {
                    "role": "user",
                    "content": "Order ORD-1009 is delayed",
                    "type": "message",
                }
            ],
            "update_delay": 15,
        }
    ]


def test_foundry_memory_store_client_creates_missing_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StoreNotFound(Exception):
        pass

    class Definition:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class Options:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class MemoryStores:
        def __init__(self) -> None:
            self.created: list[dict[str, object]] = []

        def get(self, name: str) -> object:
            raise StoreNotFound(name)

        def create(self, **kwargs: object) -> None:
            self.created.append(kwargs)

    class ProjectClient:
        def __init__(self) -> None:
            self.beta = type("Beta", (), {"memory_stores": MemoryStores()})()

    monkeypatch.setattr(
        memory_store_module, "_resource_not_found_error_type", lambda: StoreNotFound
    )
    monkeypatch.setattr(
        memory_store_module,
        "_memory_store_definition_types",
        lambda: (Definition, Options),
    )

    project_client = ProjectClient()
    FoundryMemoryStoreClient(
        HostedMemoryConfig(
            provider="foundry",
            project_endpoint="https://example.test/api/projects/demo",
            memory_store_name="order-resolution-memory",
            chat_model="gpt-memory",
            embedding_model="text-embedding-memory",
            update_delay_seconds=15,
        ),
        project_client=project_client,
    )

    created = project_client.beta.memory_stores.created
    assert len(created) == 1
    assert created[0]["name"] == "order-resolution-memory"
    definition = created[0]["definition"]
    assert isinstance(definition, Definition)
    assert definition.kwargs["chat_model"] == "gpt-memory"
    assert definition.kwargs["embedding_model"] == "text-embedding-memory"


def test_foundry_memory_store_update_failure_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MemoryUpdateError(Exception):
        pass

    class MemoryStores:
        def get(self, name: str) -> object:
            return object()

        def begin_update_memories(self, **kwargs: object) -> None:
            raise MemoryUpdateError("memory service unavailable")

    class ProjectClient:
        def __init__(self) -> None:
            self.beta = type("Beta", (), {"memory_stores": MemoryStores()})()

    monkeypatch.setattr(memory_store_module, "_azure_error_types", lambda: (MemoryUpdateError,))
    client = FoundryMemoryStoreClient(
        HostedMemoryConfig(
            provider="foundry",
            project_endpoint="https://example.test/api/projects/demo",
            memory_store_name="order-resolution-memory",
            chat_model="gpt-memory",
            embedding_model="text-embedding-memory",
            update_delay_seconds=15,
        ),
        project_client=ProjectClient(),
    )

    assert (
        client.append_conversation_item(
            thread_id="thread-1",
            role="user",
            content="Order ORD-1009 is delayed",
        )
        is False
    )
