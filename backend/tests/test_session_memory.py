from __future__ import annotations

import pytest
from workflows.session_memory import FoundrySessionMemoryStore, create_memory_store


def test_create_memory_store_foundry_placeholder() -> None:
    store = create_memory_store("foundry_memory")

    assert isinstance(store, FoundrySessionMemoryStore)
    store.append_message("thread-1", "user", "hello")
    messages = store.get_messages("thread-1")
    assert messages == [{"role": "user", "content": "hello"}]
    assert store.summarize_context("thread-1") == "user: hello"


def test_create_memory_store_rejects_invalid_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported MEMORY_PROVIDER"):
        create_memory_store("unknown")
