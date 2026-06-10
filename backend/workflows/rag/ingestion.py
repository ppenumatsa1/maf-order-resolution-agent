from __future__ import annotations

import logging

from app.modules.order_resolution.policies import default_policy_seeds
from workflows.rag.core import KnowledgeDocument, RAGProvider

logger = logging.getLogger(__name__)


class PolicyKnowledgeIngestion:
    def __init__(self, provider: RAGProvider) -> None:
        self.provider = provider

    async def ingest_defaults(self) -> None:
        for seed in default_policy_seeds():
            document = KnowledgeDocument(
                source=f"policy::{seed.issue_type}",
                title=seed.title,
                content=seed.content,
                metadata={"issue_type": seed.issue_type, "category": "resolution-policy"},
            )
            await self.provider.ingest(document)

    async def ingest_defaults_safe(self) -> None:
        try:
            await self.ingest_defaults()
        except Exception:
            logger.exception("Policy knowledge bootstrap failed; continuing with safe defaults")
