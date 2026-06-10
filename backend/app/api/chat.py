from __future__ import annotations

from uuid import uuid4

from app.models import ChatRunRequest, ChatRunResponse
from app.state import event_bus, workflow, workflow_run_repository
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from workflows.order_resolution.state import WorkflowContext

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/run", response_model=ChatRunResponse)
async def run_chat(request: ChatRunRequest) -> ChatRunResponse:
    run_id = str(uuid4())
    thread_id = request.thread_id or str(uuid4())
    session_id = request.session_id or thread_id

    context = WorkflowContext(
        run_id=run_id,
        thread_id=thread_id,
        session_id=session_id,
        customer_id=request.customer_id,
        user_message=request.message,
    )
    workflow_run_repository.create_workflow_run(
        thread_id=thread_id,
        input_text=request.message,
        session_id=session_id,
        customer_id=request.customer_id,
    )
    await workflow.start(context)

    return ChatRunResponse(run_id=run_id, thread_id=thread_id)


@router.get("/stream/{thread_id}")
async def stream_chat(thread_id: str) -> StreamingResponse:
    return StreamingResponse(
        event_bus.sse_stream(thread_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
