from __future__ import annotations

from uuid import uuid4

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["workflow_mode"] in {"maf_sdk", "foundry_hosted"}
    assert isinstance(payload["runtime_provider"], str)
    assert isinstance(payload["runtime_mode"], str)
    assert isinstance(payload["environment"], str)


def test_api_health_endpoint_alias() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "maf-orchestration-backend"


def test_chat_run_starts_workflow() -> None:
    response = client.post(
        "/api/chat/run",
        json={"message": "Order ORD-1009 is delayed by 5 days."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["thread_id"]


def test_workflow_list_accepts_both_page_size_params() -> None:
    response = client.get("/api/workflows?page=1&page_size=5")
    assert response.status_code == 200
    assert response.json()["page_size"] == 5

    legacy_response = client.get("/api/workflows?page=1&pageSize=3")
    assert legacy_response.status_code == 200
    assert legacy_response.json()["page_size"] == 3


def test_workflow_events_endpoint_is_cursor_paginated() -> None:
    run = client.post(
        "/api/chat/run",
        json={"message": "Order ORD-1001 arrived a day late."},
    )
    assert run.status_code == 200
    thread_id = run.json()["thread_id"]

    events_response = client.get(f"/api/workflows/{thread_id}/events?limit=2")
    assert events_response.status_code == 200
    payload = events_response.json()
    assert "items" in payload
    assert "pagination" in payload
    assert payload["pagination"]["limit"] == 2
    assert isinstance(payload["pagination"]["has_more"], bool)
    assert len(payload["items"]) <= 2

    event_types = {item["type"] for item in payload["items"]}
    assert "workflow.stage" in event_types or payload["pagination"]["has_more"]


def test_workflow_events_endpoint_rejects_invalid_cursor() -> None:
    run = client.post(
        "/api/chat/run",
        json={"message": "Order ORD-1001 arrived a day late."},
    )
    assert run.status_code == 200
    thread_id = run.json()["thread_id"]

    response = client.get(f"/api/workflows/{thread_id}/events?limit=2&cursor=invalid-cursor")
    assert response.status_code == 400


def test_workflow_events_endpoint_rejects_malformed_structured_cursor() -> None:
    run = client.post(
        "/api/chat/run",
        json={"message": "Order ORD-1001 arrived a day late."},
    )
    assert run.status_code == 200
    thread_id = run.json()["thread_id"]

    response = client.get(
        f"/api/workflows/{thread_id}/events?limit=2&cursor=not-a-timestamp|not-a-uuid"
    )
    assert response.status_code == 400


def test_workflow_events_endpoint_cursor_advances_without_overlap() -> None:
    run = client.post(
        "/api/chat/run",
        json={"message": "Order ORD-1001 arrived a day late."},
    )
    assert run.status_code == 200
    thread_id = run.json()["thread_id"]

    first_page = client.get(f"/api/workflows/{thread_id}/events?limit=1")
    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert len(first_payload["items"]) == 1

    first_cursor = first_payload["pagination"]["next_cursor"]
    assert first_cursor is not None

    second_page = client.get(
        f"/api/workflows/{thread_id}/events",
        params={"limit": 1, "cursor": first_cursor},
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert len(second_payload["items"]) == 1
    assert second_payload["items"][0]["id"] != first_payload["items"][0]["id"]


def test_session_messages_endpoint_supports_cursor_pagination() -> None:
    session_id = f"session-{uuid4()}"
    run = client.post(
        "/api/chat/run",
        json={
            "message": "Order ORD-1001 arrived a day late.",
            "session_id": session_id,
        },
    )
    assert run.status_code == 200

    first_page = client.get(f"/api/sessions/{session_id}/messages?limit=1")
    assert first_page.status_code == 200
    payload = first_page.json()
    assert len(payload["items"]) == 1
    assert payload["pagination"]["limit"] == 1
    assert payload["items"][0]["session_id"] == session_id

    next_cursor = payload["pagination"]["next_cursor"]
    assert next_cursor is not None

    second_page = client.get(f"/api/sessions/{session_id}/messages?limit=1&cursor={next_cursor}")
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert len(second_payload["items"]) >= 1
    assert int(second_payload["items"][0]["id"]) > int(next_cursor)


def test_session_messages_endpoint_returns_empty_page_after_last_cursor() -> None:
    session_id = f"session-{uuid4()}"
    run = client.post(
        "/api/chat/run",
        json={
            "message": "Order ORD-1001 arrived a day late.",
            "session_id": session_id,
        },
    )
    assert run.status_code == 200

    response = client.get(f"/api/sessions/{session_id}/messages?limit=2&cursor=999999")
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["pagination"]["has_more"] is False
    assert payload["pagination"]["next_cursor"] is None
