from __future__ import annotations

import logging

from app.core.config import RagProvider
from app.infrastructure.rag.core import RAGProvider
from app.infrastructure.rag.providers.azure_ai_search_provider import AzureAISearchRAGProvider
from app.infrastructure.rag.providers.foundry_provider import FoundryRAGProvider
from app.infrastructure.rag.providers.pgvector_provider import PgVectorRAGProvider

logger = logging.getLogger(__name__)


def create_rag_provider(provider: RagProvider) -> RAGProvider:
    if provider == "pgvector":
        return PgVectorRAGProvider()
    if provider == "azure_ai_search":
        logger.warning("RAG_PROVIDER=azure_ai_search uses a placeholder stub provider.")
        return AzureAISearchRAGProvider()
    if provider in {"foundry_vector", "foundry_iq"}:
        logger.warning(
            "RAG_PROVIDER=%s uses a placeholder stub provider.",
            provider,
        )
        return FoundryRAGProvider(provider_name=provider)
    raise ValueError(f"Unsupported RAG_PROVIDER: {provider}")
