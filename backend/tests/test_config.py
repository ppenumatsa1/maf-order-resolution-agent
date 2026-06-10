from __future__ import annotations

import pytest
from app.config import get_config


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

    cfg = get_config()
    assert cfg.workflow_mode == "maf_sdk"
    assert cfg.store_provider == "postgres"
    assert cfg.rag_provider == "pgvector"
    assert cfg.memory_provider == "postgres"


def test_config_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOW_MODE", "foundry_hosted")
    monkeypatch.setenv("STORE_PROVIDER", "azure_postgres")
    monkeypatch.setenv("RAG_PROVIDER", "foundry_iq")
    monkeypatch.setenv("MEMORY_PROVIDER", "foundry_memory")

    cfg = get_config()
    assert cfg.workflow_mode == "foundry_hosted"
    assert cfg.store_provider == "azure_postgres"
    assert cfg.rag_provider == "foundry_iq"
    assert cfg.memory_provider == "foundry_memory"


def test_config_rejects_invalid_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOW_MODE", "invalid-mode")
    with pytest.raises(ValueError, match="Unsupported WORKFLOW_MODE"):
        get_config()
