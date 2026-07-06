from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from azure.ai.agentserver.invocations import InvocationAgentServerHost
from opentelemetry import trace
from opentelemetry.propagate import extract
from starlette.requests import Request
from starlette.responses import JSONResponse

try:
    from foundry.conversation_shadow import (
        CONVERSATION_SHADOW_RESPONSES,
        FoundryResponsesConversationShadowClient,
        get_hosted_conversation_shadow_config,
    )
    from foundry.memory_store import (
        MEMORY_PROVIDER_FOUNDRY,
        FoundryMemoryStoreClient,
        get_hosted_memory_config,
    )
    from foundry.state_store import (
        HostedCheckpointState,
        HostedStateStore,
        build_hosted_state_store,
    )
except ImportError:
    from conversation_shadow import (
        CONVERSATION_SHADOW_RESPONSES,
        FoundryResponsesConversationShadowClient,
        get_hosted_conversation_shadow_config,
    )
    from memory_store import (
        MEMORY_PROVIDER_FOUNDRY,
        FoundryMemoryStoreClient,
        get_hosted_memory_config,
    )
    from state_store import HostedCheckpointState, HostedStateStore, build_hosted_state_store


SUPPORTED_HOSTED_PROTOCOLS = {"invocations", "dual", "responses"}


@dataclass(frozen=True)
class ResponsesProtocolTypes:
    host: type[Any]
    create_response: type[Any]
    response_context: type[Any]
    text_response: type[Any]


_CHECKPOINTS: dict[str, dict[str, Any]] = {}
_TRACING_CONFIGURED = False
_HOSTED_STATE_STORE: HostedStateStore | None = None
_MEMORY_CLIENT: FoundryMemoryStoreClient | None = None
_CONVERSATION_SHADOW_CLIENT: FoundryResponsesConversationShadowClient | None = None
logger = logging.getLogger(__name__)


def get_hosted_protocol() -> str:
    protocol = os.getenv("FOUNDRY_HOSTED_PROTOCOL", "dual").strip().lower()
    if protocol not in SUPPORTED_HOSTED_PROTOCOLS:
        allowed = "|".join(sorted(SUPPORTED_HOSTED_PROTOCOLS))
        raise ValueError(f"FOUNDRY_HOSTED_PROTOCOL must be one of: {allowed}.")
    return protocol


def _load_responses_protocol_types() -> ResponsesProtocolTypes | None:
    try:
        from azure.ai.agentserver.responses import (  # type: ignore[import-not-found]
            CreateResponse,
            ResponseContext,
            ResponsesAgentServerHost,
            TextResponse,
        )
    except ImportError:
        return None
    return ResponsesProtocolTypes(
        host=ResponsesAgentServerHost,
        create_response=CreateResponse,
        response_context=ResponseContext,
        text_response=TextResponse,
    )


def responses_protocol_blocker() -> str | None:
    if _load_responses_protocol_types() is not None:
        return None
    return (
        "azure-ai-agentserver-responses is not importable in this environment; "
        "Responses protocol routes are disabled until that package is available."
    )


def _setup_tracing() -> None:
    global _TRACING_CONFIGURED
    if _TRACING_CONFIGURED:
        return
    os.environ.setdefault("OTEL_SERVICE_NAME", "maf-foundry-hosted-agent")
    os.environ.setdefault("AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING", "true")
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if connection_string:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(connection_string=connection_string)
        except Exception:
            logger.exception("Foundry hosted tracing setup failed")
    _TRACING_CONFIGURED = True


def _hosted_state_store() -> HostedStateStore:
    global _HOSTED_STATE_STORE
    if _HOSTED_STATE_STORE is None:
        _HOSTED_STATE_STORE = build_hosted_state_store(_CHECKPOINTS)
    return _HOSTED_STATE_STORE


def _setup_memory() -> None:
    global _MEMORY_CLIENT
    config = get_hosted_memory_config()
    if config.provider == MEMORY_PROVIDER_FOUNDRY and _MEMORY_CLIENT is None:
        _MEMORY_CLIENT = FoundryMemoryStoreClient(config)
        logger.info(
            "Foundry hosted memory configured: store=%s update_delay=%ss",
            config.memory_store_name,
            config.update_delay_seconds,
        )


def _setup_conversation_shadow() -> None:
    global _CONVERSATION_SHADOW_CLIENT
    config = get_hosted_conversation_shadow_config()
    if config.provider == CONVERSATION_SHADOW_RESPONSES and _CONVERSATION_SHADOW_CLIENT is None:
        _CONVERSATION_SHADOW_CLIENT = FoundryResponsesConversationShadowClient(config)
        logger.info(
            "Foundry hosted conversation shadow configured: responses_url=%s", config.responses_url
        )


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
    if isinstance(message, dict | list):
        return ""
    return str(message).strip()


def _extract_response_input_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        if "text" in value:
            return str(value["text"]).strip()
        if "content" in value:
            return _extract_response_input_text(value["content"])
        if "message" in value:
            return str(value["message"]).strip()
        if "input" in value:
            return _extract_response_input_text(value["input"])
        return ""
    if isinstance(value, list):
        parts = [_extract_response_input_text(item) for item in value]
        return " ".join(part for part in parts if part).strip()
    content = getattr(value, "content", None)
    if content is not None:
        return _extract_response_input_text(content)
    text = getattr(value, "text", None)
    if text is not None:
        return str(text).strip()
    return str(value).strip()


def _coerce_response_payload(create_response: Any) -> dict[str, Any]:
    if isinstance(create_response, dict):
        payload = _coerce_invocation_payload(create_response)
    elif hasattr(create_response, "model_dump"):
        payload = _coerce_invocation_payload(create_response.model_dump())
    elif hasattr(create_response, "dict"):
        payload = _coerce_invocation_payload(create_response.dict())
    else:
        payload = {}
        for key in ("input", "message", "metadata"):
            value = getattr(create_response, key, None)
            if value is not None:
                payload[key] = value

    message = _extract_text(payload)
    if not message:
        message = _extract_response_input_text(payload.get("input"))
    if message:
        payload["message"] = message
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        for key in ("operation", "thread_id", "conversation_id", "session_id"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                payload.setdefault(key, value.strip())
    return payload


def _response_thread_id(create_response: Any, context: Any | None) -> str:
    for source in (create_response, context):
        if source is None:
            continue
        for key in ("thread_id", "conversation_id", "session_id", "id"):
            value = getattr(source, key, None)
            if value:
                return str(value)
    if isinstance(create_response, dict):
        for key in ("thread_id", "conversation_id", "session_id", "id"):
            value = create_response.get(key)
            if value:
                return str(value)
    return str(uuid4())


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
    ) as span:
        response = await _handle_invocation_payload(request, payload, operation)
        body = _json_response_body(response)
        span.set_attribute("workflow.status", str(body.get("status") or ""))
        span.set_attribute("workflow.event_count", len(body.get("events") or []))
        return response


async def _handle_invocation_payload(
    request: Any, payload: dict[str, Any], operation: str
) -> JSONResponse:
    _setup_memory()
    _setup_conversation_shadow()
    state_store = _hosted_state_store()
    operation = str(payload.get("operation") or "").strip().lower()
    if operation == "shadow_conversation":
        message = _extract_text(payload)
        thread_id = str(payload.get("thread_id") or request.state.session_id)
        if not message:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_request", "message": "message or input is required"},
            )
        state_store.append_conversation_item(
            thread_id=thread_id,
            role="user",
            content=message,
            metadata={"operation": "shadow_conversation", "synthetic": True},
        )
        span = trace.get_current_span()
        span.set_attribute("workflow.thread_id", thread_id)
        span.set_attribute("foundry.synthetic", True)
        span.set_attribute("workflow.status", "shadow_recorded")
        return JSONResponse({"thread_id": thread_id, "status": "shadow_recorded", "events": []})

    if operation == "resume_hitl":
        checkpoint_id = str(payload.get("checkpoint_id") or "").strip()
        decision = str(payload.get("decision") or "").strip().lower()
        reviewer = str(payload.get("reviewer") or "reviewer").strip()
        comments = payload.get("comments")
        span = trace.get_current_span()
        span.set_attribute("workflow.checkpoint_id", checkpoint_id)
        span.set_attribute("workflow.hitl.decision", decision)
        span.set_attribute("workflow.hitl.reviewer", reviewer)
        checkpoint = state_store.get_checkpoint(checkpoint_id)
        if checkpoint:
            thread_id = checkpoint.thread_id
            order_id = checkpoint.order_id
            action = checkpoint.action
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
        resolved_checkpoint = None
        if checkpoint is not None:
            resolved_checkpoint = state_store.resolve_checkpoint(
                checkpoint_id=checkpoint_id,
                decision=decision,
                reviewer=reviewer,
                comments=comments if isinstance(comments, str) else None,
            )
            if resolved_checkpoint is not None:
                events[0]["payload"].update(
                    {
                        "status": resolved_checkpoint.status,
                        "requested_at": resolved_checkpoint.requested_at,
                        "resolved_at": resolved_checkpoint.resolved_at,
                    }
                )

        if decision == "approve":
            span.set_attribute("workflow.status", "completed")
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

        span.set_attribute("workflow.status", "escalated")
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
    span = trace.get_current_span()
    span.set_attribute("workflow.thread_id", thread_id)
    span.set_attribute("workflow.order_id", order_id)
    span.set_attribute("workflow.action", action)
    span.set_attribute("workflow.requires_hitl", requires_hitl)
    state_store.append_conversation_item(
        thread_id=thread_id,
        role="user",
        content=message,
        metadata={"operation": operation or "start_workflow"},
    )
    if _MEMORY_CLIENT is not None:
        _MEMORY_CLIENT.append_conversation_item(
            thread_id=thread_id,
            role="user",
            content=message,
        )
    if _CONVERSATION_SHADOW_CLIENT is not None:
        await _CONVERSATION_SHADOW_CLIENT.append_conversation_item(
            thread_id=thread_id,
            role="user",
            content=message,
            source_operation=operation or "start_workflow",
        )
    events = _base_events(message, order_id, action, requires_hitl)

    if requires_hitl:
        checkpoint_id = str(uuid4())
        span.set_attribute("workflow.checkpoint_id", checkpoint_id)
        span.set_attribute("workflow.status", "waiting_approval")
        state_store.save_checkpoint(
            HostedCheckpointState(
                checkpoint_id=checkpoint_id,
                thread_id=thread_id,
                order_id=order_id,
                action=action,
                amount=_amount_for_order(order_id),
            )
        )
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
    span.set_attribute("workflow.status", "completed")

    return JSONResponse(
        {
            "thread_id": thread_id,
            "status": "completed",
            "events": events,
        }
    )


def _json_response_body(response: JSONResponse) -> dict[str, Any]:
    return json.loads(response.body.decode("utf-8"))


async def _handle_response_payload(
    create_response: Any,
    context: Any | None,
    text_response_type: type[Any],
) -> Any:
    _setup_tracing()
    payload = _coerce_response_payload(create_response)
    operation = str(payload.get("operation") or "start_workflow").strip().lower()
    thread_id = _response_thread_id(create_response, context)
    tracer = trace.get_tracer("foundry.hosted.order_resolution")
    with tracer.start_as_current_span(
        "foundry_hosted.response",
        attributes={
            "foundry.operation": operation,
            "workflow.thread_id": thread_id,
            "foundry.synthetic": operation == "shadow_conversation",
        },
    ) as span:
        request_context = SimpleNamespace(state=SimpleNamespace(session_id=thread_id))
        response = await _handle_invocation_payload(request_context, payload, operation)
        body = _json_response_body(response)
        span.set_attribute("workflow.status", str(body.get("status") or ""))
        span.set_attribute("workflow.event_count", len(body.get("events") or []))
        response_text = json.dumps(body)
    try:
        return text_response_type(context, create_response, text=response_text)
    except TypeError:
        return text_response_type(response_text)


def _build_responses_app(types: ResponsesProtocolTypes) -> Any:
    responses_app = types.host()

    async def handle_response(
        create_response: Any,
        context: Any | None = None,
        cancellation_signal: Any | None = None,
    ) -> Any:
        return await _handle_response_payload(
            create_response,
            context,
            types.text_response,
        )

    responses_app.response_handler(handle_response)
    return responses_app


def _build_combined_app(types: ResponsesProtocolTypes) -> Any:
    class CombinedHost(InvocationAgentServerHost, types.host):
        pass

    combined_app = CombinedHost()
    combined_app.invoke_handler(handle_invocation)

    async def handle_response(
        create_response: Any,
        context: Any | None = None,
        cancellation_signal: Any | None = None,
    ) -> Any:
        return await _handle_response_payload(
            create_response,
            context,
            types.text_response,
        )

    combined_app.response_handler(handle_response)
    return combined_app


def _create_hosted_app(protocol: str | None = None) -> Any:
    selected_protocol = protocol or get_hosted_protocol()
    types = _load_responses_protocol_types()
    if selected_protocol == "responses":
        if types is None:
            raise RuntimeError(responses_protocol_blocker())
        return _build_responses_app(types)

    if selected_protocol == "dual":
        if types is None:
            raise RuntimeError(responses_protocol_blocker())
        return _build_combined_app(types)

    invocations_app = InvocationAgentServerHost()
    invocations_app.invoke_handler(handle_invocation)
    return invocations_app


app = (
    None if os.getenv("FOUNDRY_HOSTED_SKIP_APP_INIT_FOR_TESTS") == "true" else _create_hosted_app()
)


if __name__ == "__main__":
    (_create_hosted_app() if app is None else app).run()
