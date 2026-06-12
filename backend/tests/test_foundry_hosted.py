from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

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
from foundry.main import _parse_invocation_payload


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
