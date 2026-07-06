from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


@dataclass(frozen=True)
class FoundryHostedConfig:
    invocations_url: str
    api_key: str | None
    timeout_seconds: float
    callback_token: str | None


def get_foundry_hosted_config(*, required: bool) -> FoundryHostedConfig | None:
    invocations_url = _env("FOUNDRY_HOSTED_INVOCATIONS_URL")
    if not invocations_url:
        if required:
            raise ValueError(
                "WORKFLOW_MODE=foundry_hosted requires FOUNDRY_HOSTED_INVOCATIONS_URL."
            )
        return None

    timeout_raw = _env("FOUNDRY_HOSTED_TIMEOUT_SECONDS") or "30"
    timeout_seconds = float(timeout_raw)
    if timeout_seconds <= 0:
        raise ValueError("FOUNDRY_HOSTED_TIMEOUT_SECONDS must be > 0.")

    return FoundryHostedConfig(
        invocations_url=invocations_url,
        api_key=_env("FOUNDRY_HOSTED_API_KEY"),
        timeout_seconds=timeout_seconds,
        callback_token=_env("FOUNDRY_EVENT_CALLBACK_TOKEN"),
    )
