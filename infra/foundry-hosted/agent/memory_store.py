from __future__ import annotations

import os
from dataclasses import dataclass
from logging import getLogger
from typing import Any

MEMORY_PROVIDER_NONE = "none"
MEMORY_PROVIDER_FOUNDRY = "foundry"
SUPPORTED_MEMORY_PROVIDERS = {MEMORY_PROVIDER_NONE, MEMORY_PROVIDER_FOUNDRY}
logger = getLogger(__name__)


@dataclass(frozen=True)
class HostedMemoryConfig:
    provider: str
    project_endpoint: str | None
    memory_store_name: str | None
    chat_model: str | None
    embedding_model: str | None
    update_delay_seconds: int


class FoundryMemoryStoreClient:
    def __init__(
        self,
        config: HostedMemoryConfig,
        *,
        project_client: Any | None = None,
    ) -> None:
        if config.provider != MEMORY_PROVIDER_FOUNDRY:
            raise RuntimeError("FoundryMemoryStoreClient requires provider=foundry.")
        if not config.project_endpoint or not config.memory_store_name:
            raise RuntimeError(
                "Foundry Memory Store requires project_endpoint and memory_store_name."
            )

        self._config = config
        self._client = project_client or self._build_project_client(config.project_endpoint)
        self._ensure_memory_store()

    def append_conversation_item(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
    ) -> bool:
        try:
            self._client.beta.memory_stores.begin_update_memories(
                name=self._config.memory_store_name,
                scope=thread_id,
                items=[{"role": role, "content": content, "type": "message"}],
                update_delay=self._config.update_delay_seconds,
            )
        except _azure_error_types() as exc:
            logger.warning("Foundry Memory Store update failed: %s", exc)
            return False
        return True

    def _ensure_memory_store(self) -> None:
        memory_stores = self._client.beta.memory_stores
        try:
            memory_stores.get(self._config.memory_store_name)
            return
        except _resource_not_found_error_type():
            pass

        if not self._config.chat_model or not self._config.embedding_model:
            raise RuntimeError(
                "Creating a Foundry Memory Store requires "
                "FOUNDRY_HOSTED_MEMORY_MODEL_DEPLOYMENT_NAME or "
                "FOUNDRY_HOSTED_MODEL_DEPLOYMENT_NAME, and "
                "FOUNDRY_HOSTED_MEMORY_EMBEDDINGS_DEPLOYMENT_NAME or "
                "FOUNDRY_HOSTED_EMBEDDINGS_DEPLOYMENT_NAME."
            )

        definition, options = _memory_store_definition_types()
        memory_stores.create(
            name=self._config.memory_store_name,
            definition=definition(
                chat_model=self._config.chat_model,
                embedding_model=self._config.embedding_model,
                options=options(chat_summary_enabled=True, user_profile_enabled=True),
            ),
            description="Order resolution hosted agent memory",
        )

    @staticmethod
    def _build_project_client(project_endpoint: str) -> Any:
        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise RuntimeError(
                "FOUNDRY_HOSTED_MEMORY_PROVIDER=foundry requires "
                "azure-ai-projects and azure-identity."
            ) from exc
        return AIProjectClient(
            endpoint=project_endpoint,
            credential=DefaultAzureCredential(),
        )


def get_hosted_memory_config() -> HostedMemoryConfig:
    provider = (_env("FOUNDRY_HOSTED_MEMORY_PROVIDER") or MEMORY_PROVIDER_NONE).lower()
    if provider not in SUPPORTED_MEMORY_PROVIDERS:
        raise RuntimeError(
            "FOUNDRY_HOSTED_MEMORY_PROVIDER must be one of: "
            + ", ".join(sorted(SUPPORTED_MEMORY_PROVIDERS))
        )

    config = HostedMemoryConfig(
        provider=provider,
        project_endpoint=_env("FOUNDRY_MEMORY_PROJECT_ENDPOINT")
        or _env("FOUNDRY_PROJECT_ENDPOINT")
        or _env("AZURE_AI_PROJECT_ENDPOINT"),
        memory_store_name=_env("FOUNDRY_HOSTED_MEMORY_STORE_NAME"),
        chat_model=_env("FOUNDRY_HOSTED_MEMORY_MODEL_DEPLOYMENT_NAME")
        or _env("FOUNDRY_HOSTED_MODEL_DEPLOYMENT_NAME"),
        embedding_model=_env("FOUNDRY_HOSTED_MEMORY_EMBEDDINGS_DEPLOYMENT_NAME")
        or _env("FOUNDRY_HOSTED_EMBEDDINGS_DEPLOYMENT_NAME"),
        update_delay_seconds=_env_int("FOUNDRY_HOSTED_MEMORY_UPDATE_DELAY_SECONDS", 300),
    )

    if provider == MEMORY_PROVIDER_FOUNDRY:
        missing = []
        if not config.project_endpoint:
            missing.append("FOUNDRY_PROJECT_ENDPOINT or AZURE_AI_PROJECT_ENDPOINT")
        if not config.memory_store_name:
            missing.append("FOUNDRY_HOSTED_MEMORY_STORE_NAME")
        if missing:
            raise RuntimeError(
                "FOUNDRY_HOSTED_MEMORY_PROVIDER=foundry requires " + ", ".join(missing)
            )

    return config


def _memory_store_definition_types() -> tuple[type[Any], type[Any]]:
    try:
        from azure.ai.projects.models import (
            MemoryStoreDefaultDefinition,
            MemoryStoreDefaultOptions,
        )
    except ImportError as exc:
        raise RuntimeError(
            "FOUNDRY_HOSTED_MEMORY_PROVIDER=foundry requires azure-ai-projects."
        ) from exc
    return MemoryStoreDefaultDefinition, MemoryStoreDefaultOptions


def _resource_not_found_error_type() -> type[Exception]:
    try:
        from azure.core.exceptions import ResourceNotFoundError
    except ImportError:
        return RuntimeError
    return ResourceNotFoundError


def _azure_error_types() -> tuple[type[Exception], ...]:
    try:
        from azure.core.exceptions import AzureError
    except ImportError:
        return (RuntimeError,)
    return (AzureError,)


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if parsed < 0:
        raise RuntimeError(f"{name} must be >= 0.")
    return parsed
