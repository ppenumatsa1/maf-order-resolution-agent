from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from app.api.v1.schemas.chat import ChatRunRequest, ChatRunResponse
from app.core.container import config, event_bus, order_resolution_service, workflow_run_repository
from app.modules.order_resolution.rich_events import rich_envelope_for_workflow_event
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])


async def _persisted_sse_stream(thread_id: str, *, rich: bool) -> AsyncGenerator[str, None]:
    cursor: str | None = None
    sequence = 0
    run_started = False
    while True:
        events, next_cursor, has_more = workflow_run_repository.list_workflow_events(
            thread_id,
            limit=100,
            cursor=cursor,
        )
        for event in events:
            cursor = f"{event.timestamp}|{event.id}"
            if rich:
                sequence += 1
                envelope = rich_envelope_for_workflow_event(event, sequence)
                if not run_started:
                    envelope["events"].insert(
                        0,
                        {
                            "type": "RUN_STARTED",
                            "threadId": event.thread_id,
                            "runId": event.payload.get("workflow_run_id") or event.thread_id,
                            "timestamp": envelope.get("events", [{}])[0].get("timestamp"),
                            "rawEvent": event.model_dump(),
                        },
                    )
                    run_started = True
                yield f"event: workflow.rich\ndata: {json.dumps(envelope, default=str)}\n\n"
            else:
                yield f"data: {event.model_dump_json()}\n\n"
        if has_more:
            cursor = next_cursor or cursor
            continue
        await asyncio.sleep(1)
        yield ": ping\n\n"


@router.post("/run", response_model=ChatRunResponse)
async def run_chat(request: ChatRunRequest) -> ChatRunResponse:
    return await order_resolution_service.start_chat_run(request)


@router.get("/stream/{thread_id}")
async def stream_chat(thread_id: str) -> StreamingResponse:
    stream = (
        _persisted_sse_stream(thread_id, rich=False)
        if config.runtime_target == "responses_wrapper"
        else event_bus.sse_stream(thread_id)
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/stream/{thread_id}/rich")
async def stream_chat_rich(thread_id: str) -> StreamingResponse:
    stream = (
        _persisted_sse_stream(thread_id, rich=True)
        if config.runtime_target == "responses_wrapper"
        else event_bus.rich_sse_stream(thread_id)
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
