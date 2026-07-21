from __future__ import annotations

import os
from pathlib import Path
from threading import RLock
from typing import Any

from azure.identity import DefaultAzureCredential
from psycopg import Connection
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/maf_workflow"
AZURE_POSTGRES_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


def _azure_postgres_conninfo() -> str:
    host = os.getenv("AZURE_POSTGRES_HOST", "").strip()
    database = os.getenv("AZURE_POSTGRES_DATABASE", "").strip()
    user = os.getenv("AZURE_POSTGRES_USER", "").strip()
    if not host or not database or not user:
        raise RuntimeError(
            "AZURE_POSTGRES_HOST, AZURE_POSTGRES_DATABASE, and AZURE_POSTGRES_USER "
            "must be set for managed-identity PostgreSQL authentication."
        )

    token = DefaultAzureCredential().get_token(AZURE_POSTGRES_SCOPE).token
    return make_conninfo(
        host=host,
        port=os.getenv("AZURE_POSTGRES_PORT", "5432"),
        dbname=database,
        user=user,
        password=token,
        sslmode=os.getenv("AZURE_POSTGRES_SSLMODE", "require"),
    )


class AzurePostgresConnection(Connection[Any]):
    """Gets an Entra token whenever the pool opens a physical connection."""

    @classmethod
    def connect(cls, conninfo: str = "", **kwargs: Any) -> AzurePostgresConnection:
        return super().connect(_azure_postgres_conninfo(), **kwargs)


class PostgresDatabase:
    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None
        self._schema_initialized = False
        self._lock = RLock()

    @property
    def database_url(self) -> str:
        value = os.getenv("DATABASE_URL")
        if value:
            return value
        return DEFAULT_DATABASE_URL

    @staticmethod
    def uses_azure_managed_identity() -> bool:
        return bool(os.getenv("AZURE_POSTGRES_HOST", "").strip())

    def get_pool(self) -> ConnectionPool:
        with self._lock:
            if self._pool is None:
                options: dict[str, Any] = {
                    "min_size": 0,
                    "max_size": 10,
                    "max_lifetime": 3300,
                    "max_idle": 600,
                    "open": True,
                    "kwargs": {"autocommit": True, "row_factory": dict_row},
                }
                if self.uses_azure_managed_identity():
                    self._pool = ConnectionPool(
                        conninfo="",
                        connection_class=AzurePostgresConnection,
                        **options,
                    )
                else:
                    self._pool = ConnectionPool(conninfo=self.database_url, **options)
            return self._pool

    def ensure_schema(self) -> None:
        with self._lock:
            if self._schema_initialized:
                return
            schema_path = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"
            schema_sql = schema_path.read_text(encoding="utf-8")
            pool = self.get_pool()
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(schema_sql)
            self._schema_initialized = True


postgres_db = PostgresDatabase()
