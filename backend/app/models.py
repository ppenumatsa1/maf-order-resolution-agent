from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    thread_id: str
    timestamp: str = Field(default_factory=utc_now_iso)
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatRunRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str | None = None
    session_id: str | None = None
    customer_id: str = Field(default="cust-demo")


class ChatRunResponse(BaseModel):
    run_id: str
    thread_id: str
    status: Literal["accepted"] = "accepted"


class HitlResponseRequest(BaseModel):
    checkpoint_id: str
    decision: Literal["approve", "reject"]
    reviewer: str = Field(default="human-reviewer")
    comments: str | None = None


class HitlResponseResult(BaseModel):
    accepted: bool
    checkpoint_id: str
    thread_id: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "maf-orchestration-backend"


WorkflowRunStatus = Literal[
    "running", "waiting_approval", "completed", "failed", "escalated"
]


class WorkflowRunListItem(BaseModel):
    thread_id: str
    status: WorkflowRunStatus
    input_summary: str
    created_at: str
    updated_at: str


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunListItem]
    page: int
    page_size: int
    total: int


class WorkflowRunMetadata(BaseModel):
    thread_id: str
    status: WorkflowRunStatus
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    current_stage: str | None = None


class PendingApproval(BaseModel):
    approval_id: str
    checkpoint_id: str
    action: str | None = None
    order_id: str | None = None
    amount: float | int | None = None
    question: str | None = None
    reviewer: str | None = None
    comments: str | None = None
    status: Literal["pending", "approved", "rejected"] = "pending"
    requested_at: str
    resolved_at: str | None = None


class WorkflowRunDetailsResponse(BaseModel):
    thread_id: str
    status: WorkflowRunStatus
    input: str
    events: list[WorkflowEvent]
    pending_approvals: list[PendingApproval]
    latest_output: dict[str, Any] | None = None
    metadata: WorkflowRunMetadata
