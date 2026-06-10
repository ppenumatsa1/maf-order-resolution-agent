from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

WorkflowMode = Literal["maf_sdk", "foundry_hosted"]
StoreProvider = Literal["postgres", "azure_postgres", "app_db"]
RagProvider = Literal["pgvector", "azure_ai_search", "foundry_vector", "foundry_iq"]
MemoryProvider = Literal["postgres", "foundry_memory"]


@dataclass(frozen=True)
class AppConfig:
    workflow_mode: WorkflowMode
    store_provider: StoreProvider
    rag_provider: RagProvider
    memory_provider: MemoryProvider


def _normalized(name: str, default: str) -> str:
    return (os.getenv(name, default) or default).strip().lower()


def _workflow_mode() -> WorkflowMode:
    value = _normalized("WORKFLOW_MODE", "maf_sdk")
    if value in {"maf_sdk", "foundry_hosted"}:
        return value
    raise ValueError(f"Unsupported WORKFLOW_MODE: {value}")


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


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig(
        workflow_mode=_workflow_mode(),
        store_provider=_store_provider(),
        rag_provider=_rag_provider(),
        memory_provider=_memory_provider(),
    )
