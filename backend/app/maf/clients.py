from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FoundryModelsConfig:
    project_endpoint: str
    model: str
    provider: str = "foundry"


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def get_foundry_models_config() -> FoundryModelsConfig | None:
    provider = (_env("MAF_PROVIDER") or "foundry").lower()
    if provider not in {"foundry", "foundry_models", "azure_foundry"}:
        return None

    # FOUNDRY_PROJECTS_ENDPOINT and FOUNDRY_MODEL_DEPLOYMENT_NAME are the
    # canonical Azure app-hosted contract. The other names are compatibility
    # aliases for existing local/developer environments only.
    project_endpoint = _env("FOUNDRY_PROJECTS_ENDPOINT") or _env("FOUNDRY_PROJECT_ENDPOINT")
    model = _env("FOUNDRY_MODEL_DEPLOYMENT_NAME") or _env("MAF_MODEL") or _env("FOUNDRY_MODEL")
    if not project_endpoint or not model:
        return None

    return FoundryModelsConfig(
        project_endpoint=project_endpoint,
        model=model,
        provider=provider,
    )


def has_llm_configuration() -> bool:
    return get_foundry_models_config() is not None


def create_foundry_chat_client(
    config: FoundryModelsConfig | None = None,
) -> tuple[Any, Any, FoundryModelsConfig]:
    resolved = config or get_foundry_models_config()
    if resolved is None:
        raise RuntimeError("Foundry Models configuration is not available.")

    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=resolved.project_endpoint,
        model=resolved.model,
        credential=credential,
    )
    return client, credential, resolved


def triage_mode_metadata(config: FoundryModelsConfig | None = None) -> dict[str, str]:
    resolved = config if config is not None else get_foundry_models_config()
    if resolved is None:
        return {"provider": "deterministic", "mode": "local_fallback"}
    return {
        "provider": resolved.provider,
        "mode": "foundry_models",
        "model": resolved.model,
    }
