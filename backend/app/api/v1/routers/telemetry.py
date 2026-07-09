from __future__ import annotations

import json
import os
import urllib.request
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


class TelemetryProbeRequest(BaseModel):
    event_name: str = Field(default="telemetry-probe", min_length=1, max_length=128)
    properties: dict[str, str] = Field(default_factory=dict)


class TelemetryProbeResponse(BaseModel):
    accepted: bool
    event_name: str
    app_insights_endpoint: str
    timestamp_utc: str


def _parse_connection_string(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in value.split(";"):
        segment = part.strip()
        if not segment or "=" not in segment:
            continue
        key, item_value = segment.split("=", 1)
        parsed[key.strip().lower()] = item_value.strip()
    return parsed


def _emit_event(event_name: str, properties: dict[str, str]) -> tuple[bool, str]:
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if not connection_string:
        raise HTTPException(
            status_code=400,
            detail="APPLICATIONINSIGHTS_CONNECTION_STRING is not configured.",
        )

    parsed = _parse_connection_string(connection_string)
    instrumentation_key = parsed.get("instrumentationkey")
    ingestion_endpoint = parsed.get("ingestionendpoint")
    if not instrumentation_key or not ingestion_endpoint:
        raise HTTPException(
            status_code=400,
            detail=(
                "APPLICATIONINSIGHTS_CONNECTION_STRING must include "
                "InstrumentationKey and IngestionEndpoint."
            ),
        )

    endpoint = ingestion_endpoint.rstrip("/") + "/v2/track"
    payload: dict[str, Any] = {
        "name": "Microsoft.ApplicationInsights.Event",
        "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "iKey": instrumentation_key,
        "data": {
            "baseType": "EventData",
            "baseData": {
                "name": event_name,
                "properties": {
                    "source": "backend.telemetry.probe",
                    **properties,
                },
            },
        },
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps([payload]).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3.0) as response:
            response.read()
            accepted = 200 <= response.status < 300
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Telemetry send failed: {exc}"
        ) from exc

    return accepted, ingestion_endpoint


@router.post("/probe", response_model=TelemetryProbeResponse)
def telemetry_probe(payload: TelemetryProbeRequest) -> TelemetryProbeResponse:
    accepted, ingestion_endpoint = _emit_event(payload.event_name, payload.properties)
    return TelemetryProbeResponse(
        accepted=accepted,
        event_name=payload.event_name,
        app_insights_endpoint=ingestion_endpoint,
        timestamp_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
