from __future__ import annotations

from app.models import HitlResponseRequest, HitlResponseResult
from app.state import workflow
from fastapi import APIRouter, HTTPException
from workflows.idempotency_store import IdempotencyInProgressError

router = APIRouter(prefix="/api/hitl", tags=["hitl"])


@router.post("/respond", response_model=HitlResponseResult)
async def respond_hitl(request: HitlResponseRequest) -> HitlResponseResult:
    try:
        thread_id = await workflow.handle_hitl_response(
            checkpoint_id=request.checkpoint_id,
            decision=request.decision,
            reviewer=request.reviewer,
            comments=request.comments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IdempotencyInProgressError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return HitlResponseResult(
        accepted=True, checkpoint_id=request.checkpoint_id, thread_id=thread_id
    )
