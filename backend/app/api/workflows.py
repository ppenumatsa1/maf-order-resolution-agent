from __future__ import annotations

from typing import Annotated

from app.models import (
    WorkflowRunDetailsResponse,
    WorkflowRunListResponse,
    WorkflowRunStatus,
)
from app.state import workflow_run_repository
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.get("", response_model=WorkflowRunListResponse)
async def list_workflows(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 10,
    status: Annotated[WorkflowRunStatus | None, Query()] = None,
) -> WorkflowRunListResponse:
    items, total = workflow_run_repository.list_workflow_runs(
        page=page,
        page_size=page_size,
        status=status,
    )
    return WorkflowRunListResponse(
        items=items, page=page, page_size=page_size, total=total
    )


@router.get("/{thread_id}", response_model=WorkflowRunDetailsResponse)
async def get_workflow(thread_id: str) -> WorkflowRunDetailsResponse:
    workflow_run = workflow_run_repository.get_workflow_run(thread_id)
    if not workflow_run:
        raise HTTPException(
            status_code=404, detail=f"Workflow run not found: {thread_id}"
        )
    return workflow_run
