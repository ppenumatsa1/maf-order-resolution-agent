from __future__ import annotations

from typing import Any

from app.foundry.models import FoundryEventPayload
from pydantic import BaseModel, Field


class FoundryEventIngressRequest(BaseModel):
    events: list[FoundryEventPayload] = Field(min_length=1)


class FoundryEventIngressResponse(BaseModel):
    accepted: int


class FoundryInvokeRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class FoundryInvokeResponse(BaseModel):
    ok: bool
    response: dict[str, Any]
