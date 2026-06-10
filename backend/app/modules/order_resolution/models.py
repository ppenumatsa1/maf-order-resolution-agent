from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
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


@dataclass
class WorkflowContext:
    run_id: str
    thread_id: str
    session_id: str
    customer_id: str
    user_message: str
