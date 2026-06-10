from __future__ import annotations

from app.api.v1.schemas.chat import ChatRunRequest, ChatRunResponse
from app.core.container import event_bus, order_resolution_service
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/run", response_model=ChatRunResponse)
async def run_chat(request: ChatRunRequest) -> ChatRunResponse:
    return await order_resolution_service.start_chat_run(request)


@router.get("/stream/{thread_id}")
async def stream_chat(thread_id: str) -> StreamingResponse:
    return StreamingResponse(
        event_bus.sse_stream(thread_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
