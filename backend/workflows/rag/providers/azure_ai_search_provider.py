from __future__ import annotations

from uuid import uuid4

from workflows.rag.core import KnowledgeDocument, RAGProvider, RetrievalRequest, RetrievalResult


class AzureAISearchRAGProvider(RAGProvider):
    """Placeholder provider for upcoming Azure AI Search integration."""

    async def ingest(self, document: KnowledgeDocument) -> str:
        return f"azure-ai-search-placeholder::{document.source}"

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        return RetrievalResult(
            provider="azure-ai-search-placeholder",
            query_id=f"azure-ai-search-placeholder::{uuid4()}",
            evidence=[],
        )
