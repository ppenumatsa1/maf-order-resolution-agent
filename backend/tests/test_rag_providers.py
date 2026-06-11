from __future__ import annotations

from uuid import uuid4

import pytest
from app.infrastructure.persistence import WorkflowRunRepository
from app.infrastructure.rag import KnowledgeDocument, RetrievalRequest, create_rag_provider
from app.infrastructure.rag.ingestion import PolicyKnowledgeIngestion
from app.infrastructure.rag.providers import (
    AzureAISearchRAGProvider,
    FoundryRAGProvider,
    PgVectorRAGProvider,
)


def test_create_rag_provider_pgvector() -> None:
    provider = create_rag_provider("pgvector")
    assert isinstance(provider, PgVectorRAGProvider)


@pytest.mark.asyncio
async def test_pgvector_provider_returns_seeded_policy_evidence() -> None:
    provider = create_rag_provider("pgvector")
    assert isinstance(provider, PgVectorRAGProvider)
    await PolicyKnowledgeIngestion(provider).ingest_defaults()

    thread_id = str(uuid4())
    WorkflowRunRepository().create_workflow_run(
        thread_id=thread_id,
        input_text="Order ORD-1009 is delayed by 5 days. I need compensation.",
        session_id=thread_id,
        customer_id="cust-test",
    )

    result = await provider.retrieve(
        RetrievalRequest(
            thread_id=thread_id,
            query="Policy guidance for late_delivery",
            issue_type="late_delivery",
            top_k=3,
        )
    )

    assert result.provider == "pgvector-postgres"
    assert result.evidence
    assert result.evidence[0].metadata["issue_type"] == "late_delivery"


@pytest.mark.asyncio
async def test_create_rag_provider_azure_placeholder_behavior() -> None:
    provider = create_rag_provider("azure_ai_search")
    assert isinstance(provider, AzureAISearchRAGProvider)

    document_id = await provider.ingest(
        KnowledgeDocument(source="policy::shipping", title="Shipping", content="text")
    )
    result = await provider.retrieve(
        RetrievalRequest(thread_id="thread-1", query="policy guidance", issue_type="late_delivery")
    )

    assert document_id.startswith("azure-ai-search-placeholder::")
    assert result.provider == "azure-ai-search-placeholder"
    assert result.query_id.startswith("azure-ai-search-placeholder::")
    assert result.evidence == []


@pytest.mark.parametrize("provider_name", ["foundry_vector", "foundry_iq"])
@pytest.mark.asyncio
async def test_create_rag_provider_foundry_placeholder_behavior(
    provider_name: str,
) -> None:
    provider = create_rag_provider(provider_name)
    assert isinstance(provider, FoundryRAGProvider)

    document_id = await provider.ingest(
        KnowledgeDocument(source="policy::returns", title="Returns", content="text")
    )
    result = await provider.retrieve(
        RetrievalRequest(thread_id="thread-2", query="policy guidance", issue_type=None)
    )

    assert document_id.startswith(f"{provider_name}-placeholder::")
    assert result.provider == f"{provider_name}-placeholder"
    assert result.query_id.startswith(f"{provider_name}-placeholder::")
    assert result.evidence == []


def test_create_rag_provider_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="Unsupported RAG_PROVIDER"):
        create_rag_provider("unknown-provider")  # type: ignore[arg-type]
