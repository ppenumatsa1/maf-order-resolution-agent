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
    monkeypatch.delenv("MEMORY_PROVIDER", raising=False)

    cfg = get_config()
    assert cfg.workflow_mode == "maf_sdk"
    assert cfg.store_provider == "postgres"
    assert cfg.memory_provider == "postgres"


def test_config_rejects_unsupported_persistence_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORE_PROVIDER", "azure_postgres")

    with pytest.raises(ValueError, match="Unsupported STORE_PROVIDER"):
        get_config()


def test_config_ignores_workflow_mode_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOW_MODE", "invalid-mode")
    cfg = get_config()
    assert cfg.workflow_mode == "maf_sdk"
