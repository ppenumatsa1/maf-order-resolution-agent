# Backend - MAF Sequential Multi-Agent Demo

## Run locally

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Enable MAF SDK workflow mode:

```bash
export USE_MAF_SDK=true
```

## APIs

- `POST /api/chat/run` starts sequential workflow.
- `GET /api/chat/stream/{thread_id}` streams AGUI-like SSE events.
- `POST /api/hitl/respond` approves/rejects a pending checkpoint.
- `GET /health` returns service health.

## Notes

- This implementation uses deterministic stage logic to keep the demo stable.
- MAF SDK mode is available behind `USE_MAF_SDK=true` and uses `SequentialBuilder` participant chaining.
- MCP calls support auth headers through env vars (`MCP_API_KEY`, `MCP_BEARER_TOKEN`).

## HITL Trigger Conditions

The backend emits `hitl.request` when any of these are true:

- Refund/risk amount is `>= 100`.
- The issue is classified as `damaged_item`.
- A policy string contains `manual_review`.

Test-oriented examples:

- Input with `ORD-1009` triggers HITL because deterministic order amount is `185.0`.
- Input with `ORD-1001` and a late-delivery message does not trigger HITL because amount is `79.0` and policy is low risk.

For the full matrix across both workflow implementations, see:

- `../docs/design/hitl-approval-conditions.md`
