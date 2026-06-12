from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import uuid4

from azure.ai.agentserver.invocations import InvocationAgentServerHost
from opentelemetry import trace
from opentelemetry.propagate import extract
from starlette.requests import Request
from starlette.responses import JSONResponse

app = InvocationAgentServerHost()
_CHECKPOINTS: dict[str, dict[str, Any]] = {}
_TRACING_CONFIGURED = False
logger = logging.getLogger(__name__)


def _setup_tracing() -> None:
    global _TRACING_CONFIGURED
    if _TRACING_CONFIGURED:
        return
    os.environ.setdefault("AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING", "true")
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if connection_string:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(connection_string=connection_string)
        except Exception:
            logger.exception("Foundry hosted tracing setup failed")
    _TRACING_CONFIGURED = True


def _json_object_from_string(value: str) -> dict[str, Any] | None:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    if isinstance(decoded, dict):
        return decoded
    return None


def _coerce_invocation_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return _json_object_from_string(value) or {"message": value.strip()}

    if isinstance(value, dict):
        if any(key in value for key in ("operation", "message", "checkpoint_id")):
            return value
        for key in ("payload", "input", "data", "body"):
            nested = value.get(key)
            if isinstance(nested, dict):
                return nested
            if isinstance(nested, str):
                decoded = _json_object_from_string(nested)
                if decoded is not None:
                    return decoded
        return value

    return {}


def _parse_invocation_payload(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed_payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"message": raw.decode("utf-8", errors="replace")}
    return _coerce_invocation_payload(parsed_payload)


def _extract_text(payload: dict[str, Any]) -> str:
    message = payload.get("message") or payload.get("input") or ""
    return str(message).strip()


def _order_id_for_message(message: str) -> str:
    return "ord-1009" if "1009" in message else "ord-1001"


def _is_damaged_issue(message: str) -> bool:
    return any(token in message for token in ("damaged", "broken"))


def _action_for_message(message: str) -> str:
    if _is_damaged_issue(message):
        return "issue_refund"
    if "refund" in message:
        return "issue_refund"
    if "late" in message or "delay" in message:
        return "offer_credit"
    return "provide_status_update"


def _amount_for_order(order_id: str) -> float:
    return 185.0 if order_id == "ord-1009" else 79.0


def _requires_hitl(message: str, order_id: str) -> bool:
    return _is_damaged_issue(message) or _amount_for_order(order_id) >= 100.0


def _base_events(
    message: str, order_id: str, action: str, requires_hitl: bool
) -> list[dict[str, Any]]:
    return [
        {
            "type": "workflow.stage",
            "payload": {"agent": "triage", "status": "started"},
        },
        {
            "type": "workflow.stage",
            "payload": {
                "agent": "triage",
                "status": "completed",
                "result": {"summary": f"order_id={order_id}; message={message[:120]}"},
            },
        },
        {
            "type": "tool.call",
            "payload": {
                "local_tool": "fetch_order_status/fetch_policy",
                "order": {
                    "order_id": order_id,
                    "state": "delayed" if order_id == "ord-1009" else "in_transit",
                    "total_amount": _amount_for_order(order_id),
                },
                "policy": "manual_review" if requires_hitl else "auto_resolution_allowed",
            },
        },
        {
            "type": "workflow.stage",
            "payload": {
                "agent": "resolution",
                "status": "completed",
                "result": {
                    "action": action,
                    "requires_hitl": requires_hitl,
                    "amount": _amount_for_order(order_id),
                },
            },
        },
    ]


@app.invoke_handler
async def handle_invocation(request: Request) -> JSONResponse:
    raw = await request.body()
    payload = _parse_invocation_payload(raw)

    _setup_tracing()
    operation = str(payload.get("operation") or "start_workflow").strip().lower()
    tracer = trace.get_tracer("foundry.hosted.order_resolution")
    parent_context = extract(dict(request.headers))
    with tracer.start_as_current_span(
        "foundry_hosted.invocation",
        context=parent_context,
        attributes={
            "foundry.operation": operation,
            "workflow.thread_id": str(payload.get("thread_id") or ""),
            "workflow.checkpoint_id": str(payload.get("checkpoint_id") or ""),
        },
    ):
        return await _handle_invocation_payload(request, payload, operation)


async def _handle_invocation_payload(
    request: Request, payload: dict[str, Any], operation: str
) -> JSONResponse:
    operation = str(payload.get("operation") or "").strip().lower()
    if operation == "resume_hitl":
        checkpoint_id = str(payload.get("checkpoint_id") or "").strip()
        decision = str(payload.get("decision") or "").strip().lower()
        reviewer = str(payload.get("reviewer") or "reviewer").strip()
        comments = payload.get("comments")
        checkpoint = _CHECKPOINTS.get(checkpoint_id)
        if checkpoint:
            thread_id = str(checkpoint["thread_id"])
            order_id = str(checkpoint["order_id"])
            action = str(checkpoint["action"])
        else:
            # Foundry-hosted invocation workers may be stateless across calls.
            # Accept caller-provided context so HITL resume can succeed without
            # process-local checkpoint memory.
            thread_id = str(payload.get("thread_id") or "").strip()
            order_id = str(payload.get("order_id") or "").strip()
            action = str(payload.get("action") or "").strip()
            if not thread_id or not order_id or not action:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "not_found",
                        "message": f"checkpoint not found: {checkpoint_id}",
                    },
                )
        events: list[dict[str, Any]] = [
            {
                "type": "hitl.response",
                "thread_id": thread_id,
                "payload": {
                    "checkpoint_id": checkpoint_id,
                    "decision": decision,
                    "reviewer": reviewer,
                    "comments": comments,
                },
            }
        ]

        if decision == "approve":
            events.append(
                {
                    "type": "workflow.output",
                    "thread_id": thread_id,
                    "payload": {
                        "status": "completed",
                        "message": (
                            f"Resolution complete. Action '{action}' submitted for order {order_id}."
                        ),
                    },
                }
            )
            return JSONResponse({"thread_id": thread_id, "status": "completed", "events": events})

        events.append(
            {
                "type": "workflow.output",
                "thread_id": thread_id,
                "payload": {
                    "status": "escalated",
                    "message": "Request rejected by reviewer. Escalating to human support specialist.",
                },
            }
        )
        return JSONResponse({"thread_id": thread_id, "status": "escalated", "events": events})

    message = _extract_text(payload)
    if not message:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "message": "message or input is required"},
        )

    normalized_message = message.lower()
    order_id = _order_id_for_message(normalized_message)
    action = _action_for_message(normalized_message)
    requires_hitl = _requires_hitl(normalized_message, order_id)
    thread_id = str(payload.get("thread_id") or request.state.session_id)
    events = _base_events(message, order_id, action, requires_hitl)

    if requires_hitl:
        checkpoint_id = str(uuid4())
        _CHECKPOINTS[checkpoint_id] = {
            "thread_id": thread_id,
            "order_id": order_id,
            "action": action,
        }
        events.extend(
            [
                {
                    "type": "checkpoint.created",
                    "thread_id": thread_id,
                    "payload": {"checkpoint_id": checkpoint_id, "reason": "approval_required"},
                },
                {
                    "type": "hitl.request",
                    "thread_id": thread_id,
                    "payload": {
                        "checkpoint_id": checkpoint_id,
                        "action": action,
                        "order_id": order_id,
                        "amount": _amount_for_order(order_id),
                        "question": "Approve the proposed action?",
                    },
                },
            ]
        )
        return JSONResponse(
            {"thread_id": thread_id, "status": "waiting_approval", "events": events}
        )

    events.append(
        {
            "type": "workflow.output",
            "thread_id": thread_id,
            "payload": {
                "status": "completed",
                "message": f"Resolution complete. Action '{action}' submitted for order {order_id}.",
            },
        }
    )

    return JSONResponse(
        {
            "thread_id": thread_id,
            "status": "completed",
            "events": events,
        }
    )


if __name__ == "__main__":
    app.run()
