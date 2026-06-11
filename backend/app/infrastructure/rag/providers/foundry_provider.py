from __future__ import annotations

from uuid import uuid4

from app.infrastructure.rag.core import (
    KnowledgeDocument,
    RAGProvider,
    RetrievalRequest,
    RetrievalResult,
)


class FoundryRAGProvider(RAGProvider):
    """Placeholder provider for upcoming Azure AI Foundry integrations."""

    def __init__(self, provider_name: str) -> None:
        self._provider_name = provider_name

    async def ingest(self, document: KnowledgeDocument) -> str:
        return f"{self._provider_name}-placeholder::{document.source}"

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        return RetrievalResult(
            provider=f"{self._provider_name}-placeholder",
            query_id=f"{self._provider_name}-placeholder::{uuid4()}",
            evidence=[],
        )
