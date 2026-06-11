from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.infrastructure.persistence.rag_repository import RagRepository
from app.infrastructure.rag.core import (
    KnowledgeDocument,
    RAGProvider,
    RetrievalRequest,
    RetrievalResult,
    RetrievedEvidence,
)


class PgVectorRAGProvider(RAGProvider):
    """Postgres-backed pgvector-compatible scaffold.

    This provider persists query/evidence state in Postgres and uses deterministic
    text/metadata ranking until embedding generation is wired in.
    """

    def __init__(self, repository: RagRepository | None = None) -> None:
        self.repository = repository or RagRepository()

    async def ingest(self, document: KnowledgeDocument) -> str:
        chunks = self._chunk_document(document)
        return self.repository.upsert_document_with_chunks(
            source=document.source,
            title=document.title,
            content=document.content,
            metadata=document.metadata,
            chunks=chunks,
        )

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        query_id = self.repository.create_rag_query(
            thread_id=request.thread_id,
            query=request.query,
            filters={"issue_type": request.issue_type} if request.issue_type else {},
            top_k=request.top_k,
        )
        rows = self.repository.search_chunks(
            query=request.query,
            top_k=request.top_k,
            issue_type=request.issue_type,
        )
        self.repository.save_retrieval_results(rag_query_id=query_id, rows=rows)
        evidence = [
            RetrievedEvidence(
                evidence_id=row["chunk_id"],
                document_id=row["document_id"],
                content=row["content"],
                score=row["score"],
                metadata={
                    **row.get("metadata", {}),
                    "source": row.get("source"),
                    "title": row.get("title"),
                },
            )
            for row in rows
        ]
        return RetrievalResult(provider="pgvector-postgres", query_id=query_id, evidence=evidence)

    @staticmethod
    def _chunk_document(
        document: KnowledgeDocument,
        *,
        chunk_size: int = 420,
        overlap: int = 40,
    ) -> list[dict[str, Any]]:
        text = document.content.strip()
        if not text:
            return []

        chunks: list[dict[str, Any]] = []
        start = 0
        chunk_index = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            chunk_text = text[start:end]
            chunks.append(
                {
                    "id": str(uuid4()),
                    "chunk_index": chunk_index,
                    "content": chunk_text,
                    "metadata": {**document.metadata, "source": document.source},
                    "embedding": None,
                }
            )
            if end == len(text):
                break
            start = max(0, end - overlap)
            chunk_index += 1
        return chunks
