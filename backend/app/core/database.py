from __future__ import annotations

import os
from pathlib import Path
from threading import RLock

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/maf_workflow"


RUNTIME_ENV_PATH = Path(__file__).resolve().parents[2] / "runtime" / ".env"

# Foundry-hosted packaging includes backend/runtime/.env; load it so DATABASE_URL
# is available when host-level env injection is not present.
load_dotenv(RUNTIME_ENV_PATH, override=False)


class PostgresDatabase:
    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None
        self._schema_initialized = False
        self._lock = RLock()

    @property
    def database_url(self) -> str:
        return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

    def get_pool(self) -> ConnectionPool:
        with self._lock:
            if self._pool is None:
                self._pool = ConnectionPool(
                    conninfo=self.database_url,
                    min_size=1,
                    max_size=10,
                    open=True,
                    kwargs={"autocommit": True, "row_factory": dict_row},
                )
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
