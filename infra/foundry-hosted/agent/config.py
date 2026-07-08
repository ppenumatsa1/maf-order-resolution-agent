from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class HostedTelemetryConfig:
    service_name: str
    enable_genai_tracing: bool
    app_insights_connection_string: str | None


def get_hosted_telemetry_config() -> HostedTelemetryConfig:
    return HostedTelemetryConfig(
        service_name=_env("OTEL_SERVICE_NAME") or "maf-foundry-hosted-agent",
        enable_genai_tracing=_env_bool("AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING", True),
        app_insights_connection_string=(
            _env("APPLICATIONINSIGHTS_CONNECTION_STRING")
            or _env("APPINSIGHTS_CONNECTION_STRING")
        ),
    )


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default

    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean value.")
