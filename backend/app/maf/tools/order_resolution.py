from __future__ import annotations

from dataclasses import dataclass

from app.modules.order_resolution.policies import get_policy_for_issue


@dataclass
class OrderStatus:
    order_id: str
    state: str
    total_amount: float


def fetch_order_status(order_id: str) -> OrderStatus:
    if order_id.endswith("9"):
        return OrderStatus(order_id=order_id, state="delayed", total_amount=185.0)
    return OrderStatus(order_id=order_id, state="in_transit", total_amount=79.0)


def fetch_policy(issue_type: str) -> str:
    return get_policy_for_issue(issue_type)


def submit_resolution(action: str, order_id: str) -> str:
    return f"resolution_submitted::{action}::{order_id}"

