from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FoundryOperation = Literal["start_workflow", "resume_hitl"]


class FoundryEventPayload(BaseModel):
    type: str
    thread_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None
    timestamp: str | None = None


class FoundryInvocationResponse(BaseModel):
    thread_id: str
    status: str | None = None
    events: list[FoundryEventPayload] = Field(default_factory=list)
