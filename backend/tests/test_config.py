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

    cfg = get_config()
    assert cfg.workflow_mode == "maf_sdk"
    assert cfg.store_provider == "postgres"


def test_config_uses_store_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOW_MODE", "foundry_hosted")
    monkeypatch.setenv("STORE_PROVIDER", "azure_postgres")

    cfg = get_config()
    assert cfg.workflow_mode == "maf_sdk"
    assert cfg.store_provider == "azure_postgres"


def test_config_ignores_workflow_mode_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOW_MODE", "invalid-mode")
    cfg = get_config()
    assert cfg.workflow_mode == "maf_sdk"
