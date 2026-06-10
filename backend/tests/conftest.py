from __future__ import annotations

import os

import psycopg
import pytest


def _database_available() -> bool:
    database_url = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/maf_workflow"
    )
    try:
        with psycopg.connect(database_url, connect_timeout=2):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def ensure_database_available() -> None:
    if not _database_available():
        pytest.skip("PostgreSQL is required for backend tests in this repository.")
