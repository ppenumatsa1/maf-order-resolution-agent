from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkflowContext:
    run_id: str
    thread_id: str
    session_id: str
    customer_id: str
    user_message: str
