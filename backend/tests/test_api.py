from __future__ import annotations

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_run_starts_workflow() -> None:
    response = client.post(
        "/api/chat/run",
        json={"message": "Order ORD-1009 is delayed by 5 days."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["thread_id"]
