from __future__ import annotations

from app.api.v1.routers.chat import router as chat_router
from app.api.v1.routers.health import router as health_router
from app.api.v1.routers.hitl import router as hitl_router
from app.api.v1.routers.sessions import router as sessions_router
from app.api.v1.routers.workflows import router as workflows_router
from app.core.telemetry import instrument_fastapi_app, setup_observability
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

setup_observability()

app = FastAPI(title="MAF Multi-Agent Orchestration Demo", version="0.1.0")
instrument_fastapi_app(app)

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
app.include_router(health_router)
