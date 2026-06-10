from __future__ import annotations

from app.api.chat import router as chat_router
from app.api.hitl import router as hitl_router
from app.api.sessions import router as sessions_router
from app.api.workflows import router as workflows_router
from app.models import HealthResponse
from app.state import config, rag_provider
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from observability.otel import setup_observability
from workflows.rag import PolicyKnowledgeIngestion

setup_observability()

app = FastAPI(title="MAF Multi-Agent Orchestration Demo", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(hitl_router)
app.include_router(workflows_router)
app.include_router(sessions_router)


@app.on_event("startup")
async def startup_rag_ingestion() -> None:
    if config.rag_provider == "pgvector":
        await PolicyKnowledgeIngestion(rag_provider).ingest_defaults_safe()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
