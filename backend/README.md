# Backend - MAF Order Resolution

## Runtime

FastAPI is the sole application host for the MAF workflow. The same workflow
runs locally and in the planned Azure Container Apps deployment. Foundry is
used only for triage model inference and report-only evaluation.

There is one business workflow rooted at
`app/maf/workflows/order_resolution.py`, with prompts, agents, tools,
executors, runner, and workflow kept as separate concerns.

## Run locally

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Set `FOUNDRY_PROJECTS_ENDPOINT` and `FOUNDRY_MODEL_DEPLOYMENT_NAME` to enable
model inference. Without them, only deterministic triage falls back; MAF
orchestration does not change.

## APIs

- `POST /api/chat/run`
- `GET /api/chat/stream/{thread_id}`
- `GET /api/chat/stream/{thread_id}/rich`
- `POST /api/hitl/respond`
- `GET /api/workflows`
- `GET /api/workflows/{thread_id}`
- `GET /api/workflows/{thread_id}/events`
- `GET /api/sessions/{session_id}/messages`
- `GET /health` and `GET /api/health`

## Stable SSE event types

`workflow.stage`, `tool.call`, `checkpoint.created`, `hitl.request`,
`hitl.response`, and `workflow.output`.

## HITL conditions

HITL is required when the amount/risk is at least 100, the issue is
`damaged_item`, or policy requires `manual_review`. `ORD-1009` requires HITL;
`ORD-1001` normally does not.

## Evaluation

`make eval-backend` is the deterministic contract gate. `make eval-foundry`
captures canonical FastAPI workflow results for a non-blocking, report-only
Foundry evaluation.
