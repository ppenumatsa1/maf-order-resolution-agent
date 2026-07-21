from __future__ import annotations

import pytest
from app.infrastructure.persistence.session_memory import create_memory_store


def test_create_memory_store_rejects_removed_foundry_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported MEMORY_PROVIDER"):
        create_memory_store("foundry_memory")


def test_create_memory_store_rejects_invalid_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported MEMORY_PROVIDER"):
        create_memory_store("unknown")
