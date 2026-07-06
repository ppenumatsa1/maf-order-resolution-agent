from __future__ import annotations

import os
from dataclasses import dataclass
from logging import getLogger
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential
from opentelemetry import trace
from opentelemetry.propagate import inject

CONVERSATION_SHADOW_NONE = "none"
CONVERSATION_SHADOW_RESPONSES = "responses"
SUPPORTED_CONVERSATION_SHADOW_PROVIDERS = {
    CONVERSATION_SHADOW_NONE,
    CONVERSATION_SHADOW_RESPONSES,
}
logger = getLogger(__name__)


@dataclass(frozen=True)
class HostedConversationShadowConfig:
    provider: str
    responses_url: str | None
    api_key: str | None
    timeout_seconds: float


class FoundryResponsesConversationShadowClient:
    def __init__(
        self,
        config: HostedConversationShadowConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
        credential: Any | None = None,
    ) -> None:
        if config.provider != CONVERSATION_SHADOW_RESPONSES:
            raise RuntimeError(
                "FoundryResponsesConversationShadowClient requires provider=responses."
            )
        if not config.responses_url:
            raise RuntimeError(
                "FOUNDRY_HOSTED_CONVERSATION_SHADOW_PROVIDER=responses requires "
                "FOUNDRY_HOSTED_RESPONSES_URL or a derivable FOUNDRY_HOSTED_INVOCATIONS_URL."
            )

        self._config = config
        self._responses_url = config.responses_url
        self._http_client = http_client
        self._credential = credential

    async def append_conversation_item(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        source_operation: str,
    ) -> bool:
        payload = {
            "input": [
                {
                    "role": role,
                    "content": [{"type": "input_text", "text": content}],
                }
            ],
            "metadata": {
                "operation": "shadow_conversation",
                "thread_id": thread_id,
                "source_operation": source_operation,
                "source_protocol": "invocations",
                "synthetic": "true",
            },
        }
        headers = self._headers()
        close_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(
            timeout=self._config.timeout_seconds
        )
        tracer = trace.get_tracer("foundry.hosted.order_resolution")
        try:
            with tracer.start_as_current_span(
                "foundry_hosted.responses_shadow",
                attributes={
                    "workflow.thread_id": thread_id,
                    "foundry.operation": "shadow_conversation",
                    "foundry.source_operation": source_operation,
                    "foundry.source_protocol": "invocations",
                    "foundry.synthetic": True,
                },
            ) as span:
                response = await client.post(
                    self._responses_url,
                    json=payload,
                    headers=headers,
                )
                span.set_attribute("http.response.status_code", response.status_code)
                response.raise_for_status()
        except (httpx.HTTPError, RuntimeError) as exc:
            logger.warning("Foundry Responses conversation shadow failed: %s", exc)
            return False
        finally:
            if close_client:
                await client.aclose()
        return True

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        inject(headers)
        responses_url = self._config.responses_url or ""
        if "services.ai.azure.com" in responses_url:
            headers["Foundry-Features"] = "HostedAgents=V1Preview"
        if self._config.api_key:
            api_key = self._config.api_key.strip()
            if api_key.lower().startswith("bearer "):
                headers["Authorization"] = api_key
            elif _looks_like_jwt(api_key):
                headers["Authorization"] = f"Bearer {api_key}"
            else:
                headers["api-key"] = api_key
        elif "services.ai.azure.com" in responses_url:
            headers["Authorization"] = f"Bearer {self._get_foundry_bearer_token()}"
        return headers

    def _get_foundry_bearer_token(self) -> str:
        credential = self._credential or DefaultAzureCredential(
            exclude_interactive_browser_credential=True
        )
        token = credential.get_token("https://ai.azure.com/.default")
        return token.token


def get_hosted_conversation_shadow_config() -> HostedConversationShadowConfig:
    provider = (
        _env("FOUNDRY_HOSTED_CONVERSATION_SHADOW_PROVIDER") or CONVERSATION_SHADOW_NONE
    ).lower()
    if provider not in SUPPORTED_CONVERSATION_SHADOW_PROVIDERS:
        raise RuntimeError(
            "FOUNDRY_HOSTED_CONVERSATION_SHADOW_PROVIDER must be one of: "
            + ", ".join(sorted(SUPPORTED_CONVERSATION_SHADOW_PROVIDERS))
        )

    responses_url = _env("FOUNDRY_HOSTED_RESPONSES_URL") or _derive_responses_url(
        _env("FOUNDRY_HOSTED_INVOCATIONS_URL")
    )
    config = HostedConversationShadowConfig(
        provider=provider,
        responses_url=responses_url,
        api_key=_env("FOUNDRY_HOSTED_RESPONSES_API_KEY")
        or _env("FOUNDRY_HOSTED_API_KEY"),
        timeout_seconds=_env_float("FOUNDRY_HOSTED_RESPONSES_TIMEOUT_SECONDS", 3.0),
    )
    if provider == CONVERSATION_SHADOW_RESPONSES and not config.responses_url:
        raise RuntimeError(
            "FOUNDRY_HOSTED_CONVERSATION_SHADOW_PROVIDER=responses requires "
            "FOUNDRY_HOSTED_RESPONSES_URL or FOUNDRY_HOSTED_INVOCATIONS_URL ending in "
            "/invocations."
        )
    return config


def _derive_responses_url(invocations_url: str | None) -> str | None:
    if not invocations_url:
        return None
    stripped = invocations_url.rstrip("/")
    if not stripped.endswith("/invocations"):
        return None
    return stripped[: -len("/invocations")] + "/responses"


def _looks_like_jwt(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 3:
        return False
    return all(part.strip() for part in parts)


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_float(name: str, default: float) -> float:
    value = _env(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number.") from exc
    if parsed <= 0:
        raise RuntimeError(f"{name} must be > 0.")
    return parsed
