from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.api.v1.schemas.chat import ChatRunRequest
from app.api.v1.schemas.hitl import HitlResponseRequest
from app.core.container import order_resolution_service, workflow_run_repository
from app.core.telemetry import setup_observability


@dataclass(frozen=True)
class _ParsedInput:
    conversation_id: str
    message: str | None
    decision: str | None
    checkpoint_id: str | None


def _load_responses_types() -> tuple[type[Any], type[Any], type[Any], type[Any]]:
    # Compatibility shim for hosted images where agentserver-core is missing
    # CHAT_ISOLATION_KEY expected by azure-ai-agentserver-responses.
    try:
        from azure.ai.agentserver.core import _platform_headers as platform_headers  # type: ignore[import-not-found]

        if not hasattr(platform_headers, "CHAT_ISOLATION_KEY"):
            setattr(platform_headers, "CHAT_ISOLATION_KEY", "x-agent-chat-isolation-key")
    except Exception:
        # Let the canonical import below raise with its own actionable error.
        pass

    from azure.ai.agentserver.responses import (  # type: ignore[import-not-found]
        CreateResponse,
        ResponseContext,
        ResponsesAgentServerHost,
        TextResponse,
    )

    return ResponsesAgentServerHost, CreateResponse, ResponseContext, TextResponse


def _coerce_payload(create_response: Any) -> dict[str, Any]:
    if isinstance(create_response, dict):
        return dict(create_response)
    if hasattr(create_response, "model_dump"):
        return create_response.model_dump()
    if hasattr(create_response, "dict"):
        return create_response.dict()
    return {}


def _nested_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        if "text" in value:
            return _nested_text(value["text"])
        if "content" in value:
            return _nested_text(value["content"])
        if "input" in value:
            return _nested_text(value["input"])
        if "message" in value:
            return _nested_text(value["message"])
        if "output" in value:
            return _nested_text(value["output"])
        return ""
    if isinstance(value, list):
        parts = [_nested_text(item) for item in value]
        return " ".join(part for part in parts if part).strip()
    return str(value).strip()


def _coerce_conversation_id(payload: dict[str, Any], context: Any | None) -> str:
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        for key in ("conversation_id", "thread_id", "session_id"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("conversation_id", "thread_id", "session_id", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if context is not None:
        for key in ("conversation_id", "thread_id", "session_id", "id", "response_id"):
            value = getattr(context, key, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(uuid4())


def _iter_input_items(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    raw_input = payload.get("input")
    if isinstance(raw_input, dict):
        return [raw_input]
    if isinstance(raw_input, list):
        return [item for item in raw_input if isinstance(item, dict)]
    return []


def _parse_function_call_output(items: Iterable[dict[str, Any]]) -> tuple[str | None, str | None]:
    checkpoint_id: str | None = None
    decision: str | None = None
    for item in items:
        if str(item.get("type", "")).strip().lower() != "function_call_output":
            continue
        call_id = item.get("call_id")
        if isinstance(call_id, str) and call_id.strip():
            checkpoint_id = call_id.strip()
        output = item.get("output")
        if isinstance(output, dict):
            out_checkpoint = output.get("checkpoint_id")
            out_decision = output.get("decision")
            if isinstance(out_checkpoint, str) and out_checkpoint.strip():
                checkpoint_id = out_checkpoint.strip()
            if isinstance(out_decision, str):
                lowered = out_decision.strip().lower()
                if lowered in {"approve", "reject"}:
                    decision = lowered
        elif isinstance(output, str):
            lowered = output.strip().lower()
            if lowered in {"approve", "reject"}:
                decision = lowered
    return checkpoint_id, decision


def _decision_from_text(message: str | None) -> str | None:
    if not message:
        return None
    lowered = message.strip().lower()
    if lowered in {"approve", "approved", "yes"}:
        return "approve"
    if lowered in {"reject", "rejected", "no"}:
        return "reject"
    return None


def _pending_checkpoint_id(thread_id: str) -> str | None:
    details = workflow_run_repository.get_workflow_run(thread_id)
    if not details:
        return None
    for approval in details.pending_approvals:
        if approval.status == "pending":
            return approval.checkpoint_id
    return None


def _parse_input(create_response: Any, context: Any | None) -> _ParsedInput:
    payload = _coerce_payload(create_response)
    metadata = payload.get("metadata")
    message = _nested_text(payload.get("message")) or _nested_text(payload.get("input"))
    checkpoint_id: str | None = None
    decision: str | None = None
    if isinstance(metadata, dict):
        maybe_checkpoint = metadata.get("checkpoint_id")
        if isinstance(maybe_checkpoint, str) and maybe_checkpoint.strip():
            checkpoint_id = maybe_checkpoint.strip()
        maybe_decision = metadata.get("decision")
        if isinstance(maybe_decision, str):
            lowered = maybe_decision.strip().lower()
            if lowered in {"approve", "reject"}:
                decision = lowered
    input_checkpoint, input_decision = _parse_function_call_output(_iter_input_items(payload))
    if input_checkpoint:
        checkpoint_id = input_checkpoint
    if input_decision:
        decision = input_decision
    decision = decision or _decision_from_text(message)
    return _ParsedInput(
        conversation_id=_coerce_conversation_id(payload, context),
        message=message or None,
        decision=decision,
        checkpoint_id=checkpoint_id,
    )


def _serialize_workflow(thread_id: str) -> dict[str, Any]:
    details = workflow_run_repository.get_workflow_run(thread_id)
    if details is None:
        return {
            "thread_id": thread_id,
            "status": "failed",
            "events": [],
            "pending_approvals": [],
            "latest_output": None,
            "message": "Workflow run not found.",
        }
    return {
        "thread_id": details.thread_id,
        "status": details.status,
        "events": [event.model_dump() for event in details.events],
        "pending_approvals": [approval.model_dump() for approval in details.pending_approvals],
        "latest_output": details.latest_output,
        "message": (
            str(details.latest_output.get("message"))
            if isinstance(details.latest_output, dict) and details.latest_output.get("message")
            else ""
        ),
    }


async def _run_from_responses(
    create_response: Any, context: Any | None, text_response: type[Any]
) -> Any:
    parsed = _parse_input(create_response, context)
    if parsed.decision:
        checkpoint_id = parsed.checkpoint_id or _pending_checkpoint_id(parsed.conversation_id)
        if checkpoint_id is None:
            payload = {
                "thread_id": parsed.conversation_id,
                "status": "failed",
                "events": [],
                "pending_approvals": [],
                "message": "No pending approval found for this conversation.",
            }
        else:
            await order_resolution_service.respond_hitl(
                HitlResponseRequest(
                    checkpoint_id=checkpoint_id,
                    decision=parsed.decision,
                    reviewer="foundry-conversation",
                    comments="decision received from responses conversation",
                )
            )
            payload = _serialize_workflow(parsed.conversation_id)
    elif parsed.message:
        await order_resolution_service.start_chat_run(
            ChatRunRequest(
                message=parsed.message,
                thread_id=parsed.conversation_id,
                session_id=parsed.conversation_id,
                customer_id="foundry-hosted",
            )
        )
        payload = _serialize_workflow(parsed.conversation_id)
    else:
        payload = {
            "thread_id": parsed.conversation_id,
            "status": "failed",
            "events": [],
            "pending_approvals": [],
            "message": "message or input is required",
        }
    response_text = json.dumps(payload)
    return text_response(context, create_response, text=response_text)


def _build_app() -> Any:
    ResponsesAgentServerHost, _, _, TextResponse = _load_responses_types()
    host = ResponsesAgentServerHost()

    async def handler(
        create_response: Any,
        context: Any | None = None,
        cancellation_signal: Any | None = None,
    ) -> Any:
        return await _run_from_responses(create_response, context, TextResponse)

    host.response_handler(handler)
    return host


def _initialize_app() -> Any:
    setup_observability()
    return _build_app()


app = None if os.getenv("FOUNDRY_HOSTED_SKIP_APP_INIT_FOR_TESTS") == "true" else _initialize_app()


if __name__ == "__main__":
    (_initialize_app() if app is None else app).run()
