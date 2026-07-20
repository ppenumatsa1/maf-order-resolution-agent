from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

WorkflowMode = Literal["maf_sdk"]
StoreProvider = Literal["postgres", "azure_postgres", "app_db"]


@dataclass(frozen=True)
class AppConfig:
    workflow_mode: WorkflowMode
    store_provider: StoreProvider


def _normalized(name: str, default: str) -> str:
    return (os.getenv(name, default) or default).strip().lower()


def _store_provider() -> StoreProvider:
    value = _normalized("STORE_PROVIDER", "postgres")
    if value in {"postgres", "azure_postgres", "app_db"}:
        return value
    raise ValueError(f"Unsupported STORE_PROVIDER: {value}")


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig(
        workflow_mode="maf_sdk",
        store_provider=_store_provider(),
    )
