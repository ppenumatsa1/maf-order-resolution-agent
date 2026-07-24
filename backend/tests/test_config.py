from __future__ import annotations

import pytest
from app.core.config import get_config


@pytest.fixture(autouse=True)
def clear_config_cache():
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def test_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKFLOW_MODE", raising=False)
    monkeypatch.delenv("STORE_PROVIDER", raising=False)
    monkeypatch.delenv("RAG_PROVIDER", raising=False)
    monkeypatch.delenv("MEMORY_PROVIDER", raising=False)
    monkeypatch.delenv("RUNTIME_TARGET", raising=False)

    cfg = get_config()
    assert cfg.workflow_mode == "maf_sdk"
    assert cfg.store_provider == "postgres"
    assert cfg.rag_provider == "pgvector"
    assert cfg.memory_provider == "postgres"
    assert cfg.runtime_target == "local_maf"


def test_config_uses_env_for_store_rag_and_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOW_MODE", "foundry_hosted")
    monkeypatch.setenv("STORE_PROVIDER", "azure_postgres")
    monkeypatch.setenv("RAG_PROVIDER", "foundry_iq")
    monkeypatch.setenv("MEMORY_PROVIDER", "foundry_memory")

    cfg = get_config()
    assert cfg.workflow_mode == "maf_sdk"
    assert cfg.store_provider == "azure_postgres"
    assert cfg.rag_provider == "foundry_iq"
    assert cfg.memory_provider == "foundry_memory"


def test_config_ignores_workflow_mode_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOW_MODE", "invalid-mode")
    cfg = get_config()
    assert cfg.workflow_mode == "maf_sdk"


def test_config_selects_responses_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_TARGET", "responses_wrapper")

    assert get_config().runtime_target == "responses_wrapper"
