from __future__ import annotations

from dataclasses import dataclass


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
    policies = {
        "late_delivery": "refund_allowed_if_delay_exceeds_3_days",
        "damaged_item": "replacement_or_full_refund_with_photo_proof",
        "wrong_item": "free_replacement_and_return_label",
    }
    return policies.get(issue_type, "manual_review_required")


def submit_resolution(action: str, order_id: str) -> str:
    return f"resolution_submitted::{action}::{order_id}"
