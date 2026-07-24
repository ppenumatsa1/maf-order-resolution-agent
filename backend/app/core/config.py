from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

WorkflowMode = Literal["maf_sdk"]
StoreProvider = Literal["postgres", "azure_postgres", "app_db"]
RagProvider = Literal["pgvector", "azure_ai_search", "foundry_vector", "foundry_iq"]
MemoryProvider = Literal["postgres", "foundry_memory"]
RuntimeTarget = Literal["local_maf", "responses_wrapper"]


@dataclass(frozen=True)
class AppConfig:
    workflow_mode: WorkflowMode
    store_provider: StoreProvider
    rag_provider: RagProvider
    memory_provider: MemoryProvider
    runtime_target: RuntimeTarget = "local_maf"


def _normalized(name: str, default: str) -> str:
    return (os.getenv(name, default) or default).strip().lower()


def _store_provider() -> StoreProvider:
    value = _normalized("STORE_PROVIDER", "postgres")
    if value in {"postgres", "azure_postgres", "app_db"}:
        return value
    raise ValueError(f"Unsupported STORE_PROVIDER: {value}")


def _rag_provider() -> RagProvider:
    value = _normalized("RAG_PROVIDER", "pgvector")
    if value in {"pgvector", "azure_ai_search", "foundry_vector", "foundry_iq"}:
        return value
    raise ValueError(f"Unsupported RAG_PROVIDER: {value}")


def _memory_provider() -> MemoryProvider:
    value = _normalized("MEMORY_PROVIDER", "postgres")
    if value in {"postgres", "foundry_memory"}:
        return value
    raise ValueError(f"Unsupported MEMORY_PROVIDER: {value}")


def _runtime_target() -> RuntimeTarget:
    value = _normalized("RUNTIME_TARGET", "local_maf")
    if value in {"local_maf", "responses_wrapper"}:
        return value
    raise ValueError(f"Unsupported RUNTIME_TARGET: {value}")


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig(
        workflow_mode="maf_sdk",
        store_provider=_store_provider(),
        rag_provider=_rag_provider(),
        memory_provider=_memory_provider(),
        runtime_target=_runtime_target(),
    )
