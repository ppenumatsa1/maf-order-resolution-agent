from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.database import postgres_db


class RagRepository:
    def __init__(self) -> None:
        postgres_db.ensure_schema()
        self._pool = postgres_db.get_pool()

    def upsert_document_with_chunks(
        self,
        *,
        source: str,
        title: str,
        content: str,
        metadata: dict[str, Any],
        chunks: Sequence[dict[str, Any]],
    ) -> str:
        with self._pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id FROM documents
                        WHERE source = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (source,),
                    )
                    row = cur.fetchone()
                    document_id = str(row["id"]) if row else str(uuid4())
                    if row:
                        cur.execute(
                            """
                            UPDATE documents
                            SET title = %s,
                                content = %s,
                                metadata = %s::jsonb
                            WHERE id = %s::uuid
                            """,
                            (title, content, json.dumps(metadata), document_id),
                        )
                        cur.execute(
                            "DELETE FROM document_chunks WHERE document_id = %s::uuid",
                            (document_id,),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO documents (id, source, title, content, metadata)
                            VALUES (%s::uuid, %s, %s, %s, %s::jsonb)
                            """,
                            (document_id, source, title, content, json.dumps(metadata)),
                        )

                    for chunk in chunks:
                        cur.execute(
                            """
                            INSERT INTO document_chunks (
                                id, document_id, chunk_index, content, metadata, embedding
                            ) VALUES (%s::uuid, %s::uuid, %s, %s, %s::jsonb, %s::jsonb)
                            """,
                            (
                                chunk["id"],
                                document_id,
                                chunk["chunk_index"],
                                chunk["content"],
                                json.dumps(chunk.get("metadata", {})),
                                json.dumps(chunk.get("embedding"))
                                if chunk.get("embedding") is not None
                                else None,
                            ),
                        )
        return document_id

    def create_rag_query(
        self,
        *,
        thread_id: str | None,
        query: str,
        filters: dict[str, Any],
        top_k: int,
    ) -> str:
        rag_query_id = str(uuid4())
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO rag_queries (id, thread_id, query, filters, top_k)
                    VALUES (%s::uuid, %s, %s, %s::jsonb, %s)
                    """,
                    (rag_query_id, thread_id, query, json.dumps(filters), top_k),
                )
        return rag_query_id

    def search_chunks(
        self,
        *,
        query: str,
        top_k: int,
        issue_type: str | None,
    ) -> list[dict[str, Any]]:
        like_query = f"%{query}%"
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        dc.id AS chunk_id,
                        dc.document_id,
                        dc.content,
                        dc.metadata,
                        d.source,
                        d.title,
                        (
                            CASE WHEN dc.content ILIKE %s THEN 1.0 ELSE 0.0 END
                            + CASE
                                WHEN %s IS NOT NULL
                                 AND COALESCE(dc.metadata->>'issue_type', d.metadata->>'issue_type') = %s
                                THEN 0.75
                                ELSE 0.0
                              END
                            + CASE
                                WHEN %s IS NOT NULL
                                 AND d.title ILIKE CONCAT('%%', %s, '%%')
                                THEN 0.25
                                ELSE 0.0
                              END
                        ) AS score
                    FROM document_chunks dc
                    INNER JOIN documents d ON d.id = dc.document_id
                    WHERE (
                        %s IS NULL
                        OR COALESCE(dc.metadata->>'issue_type', d.metadata->>'issue_type') = %s
                    )
                    ORDER BY score DESC, dc.created_at DESC
                    LIMIT %s
                    """,
                    (
                        like_query,
                        issue_type,
                        issue_type,
                        issue_type,
                        issue_type,
                        issue_type,
                        issue_type,
                        top_k,
                    ),
                )
                rows = cur.fetchall()

        return [
            {
                "chunk_id": str(row["chunk_id"]),
                "document_id": str(row["document_id"]),
                "content": row["content"],
                "metadata": row["metadata"] or {},
                "source": row["source"],
                "title": row["title"],
                "score": float(row["score"] or 0.0),
            }
            for row in rows
        ]

    def save_retrieval_results(
        self,
        *,
        rag_query_id: str,
        rows: Sequence[dict[str, Any]],
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                for rank, row in enumerate(rows, start=1):
                    cur.execute(
                        """
                        INSERT INTO rag_retrieval_results (
                            id, rag_query_id, chunk_id, score, rank, metadata, created_at
                        ) VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s)
                        """,
                        (
                            str(uuid4()),
                            rag_query_id,
                            row["chunk_id"],
                            row.get("score"),
                            rank,
                            json.dumps(
                                {
                                    "source": row.get("source"),
                                    "title": row.get("title"),
                                }
                            ),
                            created_at,
                        ),
                    )
