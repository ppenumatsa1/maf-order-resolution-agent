from __future__ import annotations

from app.core import database


def test_azure_postgres_conninfo_uses_fresh_entra_token(
    monkeypatch,
) -> None:
    issued_tokens = iter(("token-one", "token-two"))

    class Credential:
        def get_token(self, scope: str):
            assert scope == database.AZURE_POSTGRES_SCOPE
            return type("Token", (), {"token": next(issued_tokens)})()

    monkeypatch.setattr(database, "DefaultAzureCredential", Credential)
    monkeypatch.setenv("AZURE_POSTGRES_HOST", "server.postgres.database.azure.com")
    monkeypatch.setenv("AZURE_POSTGRES_DATABASE", "maf_workflow")
    monkeypatch.setenv("AZURE_POSTGRES_USER", "maf-backend")

    first = database._azure_postgres_conninfo()
    second = database._azure_postgres_conninfo()

    assert "password=token-one" in first
    assert "password=token-two" in second
    assert "sslmode=require" in first


def test_managed_identity_mode_requires_complete_postgres_configuration(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AZURE_POSTGRES_HOST", "server.postgres.database.azure.com")
    monkeypatch.delenv("AZURE_POSTGRES_DATABASE", raising=False)
    monkeypatch.delenv("AZURE_POSTGRES_USER", raising=False)

    try:
        database._azure_postgres_conninfo()
    except RuntimeError as exc:
        assert "AZURE_POSTGRES_HOST" in str(exc)
    else:
        raise AssertionError("Expected managed-identity configuration validation to fail.")


def test_managed_identity_mode_is_selected_only_with_azure_host(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AZURE_POSTGRES_HOST", raising=False)
    assert database.PostgresDatabase.uses_azure_managed_identity() is False

    monkeypatch.setenv("AZURE_POSTGRES_HOST", "server.postgres.database.azure.com")
    assert database.PostgresDatabase.uses_azure_managed_identity() is True


def test_connection_pool_does_not_retain_minimum_idle_connections(monkeypatch) -> None:
    created: list[dict[str, object]] = []

    class Pool:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)

    monkeypatch.setattr(database, "ConnectionPool", Pool)

    database.PostgresDatabase().get_pool()

    assert created[0]["min_size"] == 0
