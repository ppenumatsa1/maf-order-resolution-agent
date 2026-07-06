from __future__ import annotations

import os

from app.api.v1.schemas.foundry import (
    FoundryEventIngressRequest,
    FoundryEventIngressResponse,
    FoundryInvokeRequest,
    FoundryInvokeResponse,
)
from app.core.container import event_bus
from app.foundry.client import FoundryHostedClient
from app.foundry.config import get_foundry_hosted_config
from app.modules.order_resolution.models import WorkflowEvent
from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api/foundry", tags=["foundry"])


def _workflow_mode() -> str:
    return (os.getenv("WORKFLOW_MODE", "maf_sdk") or "maf_sdk").strip().lower()


def _required_callback_token() -> str:
    token = (os.getenv("FOUNDRY_EVENT_CALLBACK_TOKEN") or "").strip()
    if not token:
        raise HTTPException(
            status_code=503,
            detail="FOUNDRY_EVENT_CALLBACK_TOKEN is not configured for event ingress.",
        )
    return token


@router.post("/invoke", response_model=FoundryInvokeResponse)
async def invoke_foundry(payload: FoundryInvokeRequest) -> FoundryInvokeResponse:
    if not payload.payload:
        raise HTTPException(status_code=422, detail="payload must include at least one field.")

    config = get_foundry_hosted_config(required=False)

    if config is None:
        raise HTTPException(
            status_code=503,
            detail="FOUNDRY_HOSTED_INVOCATIONS_URL is not configured.",
        )

    client = FoundryHostedClient(config)
    try:
        response = await client.invoke_raw(payload.payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return FoundryInvokeResponse(ok=True, response=response)


@router.post("/events", response_model=FoundryEventIngressResponse)
async def ingest_events(
    request: FoundryEventIngressRequest,
    x_foundry_callback_token: str = Header(default=""),
) -> FoundryEventIngressResponse:
    if _workflow_mode() != "foundry_hosted":
        raise HTTPException(status_code=404, detail="Foundry event ingress is disabled.")

    required_token = _required_callback_token()
    if x_foundry_callback_token != required_token:
        raise HTTPException(status_code=401, detail="Invalid Foundry callback token.")

    for event in request.events:
        if not event.thread_id:
            raise HTTPException(status_code=422, detail="Foundry event thread_id is required.")
        workflow_event = WorkflowEvent(
            type=event.type,
            thread_id=event.thread_id,
            payload=event.payload,
        )
        if event.id:
            workflow_event.id = event.id
        if event.timestamp:
            workflow_event.timestamp = event.timestamp
        await event_bus.publish(workflow_event)

    return FoundryEventIngressResponse(accepted=len(request.events))
