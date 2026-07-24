# Tech Stack

## Backend

- Python 3.10+
- FastAPI + Uvicorn
- Pydantic v2
- httpx for MCP HTTP tool calls
- OpenTelemetry SDK + OTLP exporter
- Azure Monitor OpenTelemetry exporter for public Application Insights

## Frontend

- React 18
- Vite 5
- TypeScript

## Data and Durability

- PostgreSQL as the durable source of truth for workflow runs, events, conversation messages, checkpoints, approvals, sessions, and eval records
- Psycopg v3 + connection pooling for backend persistence access

## Integration

- MCP via streamable HTTP endpoint (`MCP_SERVER_URL`)
- OTEL exporters configurable by environment variables
- Public Azure: Foundry Responses, Container Apps, managed identity, PostgreSQL
  Flexible Server, and Application Insights
- App Insights enabled through `APPLICATIONINSIGHTS_CONNECTION_STRING`; FastAPI
  health and SSE request spans are excluded to keep workflow telemetry visible

## Skills Baseline

Use only the task-specific skills below; do not load the full Microsoft skills catalog.
The curated baseline contains five vendored Microsoft skills and two local
(repository-owned) skills.

| Skill | Use for | Source |
|---|---|---|
| `agent-framework-foundry-py` | This service's `FoundryChatClient`, `SequentialBuilder`, middleware, streamed telemetry, and checkpoint-backed HITL work | Repository-owned |
| `azure-ai-projects-py` | Azure AI Foundry project, deployment, and evaluation work | Microsoft `skills` |
| `azure-identity-py` | `DefaultAzureCredential`, managed identity, and Entra authentication | Microsoft `skills` |
| `azure-monitor-opentelemetry-py` | Application Insights and Azure Monitor OpenTelemetry work | Microsoft `skills` |
| `fastapi-router-py` | FastAPI HTTP route work | Microsoft `skills` |
| `pydantic-models-py` | Pydantic v2 API contract work | Microsoft `skills` |
| `postgres-psycopg-py` | PostgreSQL, Psycopg, and Azure PostgreSQL workflow-audit persistence | Repository-owned |

The five Microsoft skills are vendored from
[`microsoft/skills`](https://github.com/microsoft/skills) commit
`c33193b1b2dd14d5946e3c6213fd095ffa5b31df`. Refresh them deliberately from that
source, preserving each complete skill directory and reviewing upstream changes before updating
the pinned revision.

`agent-framework-foundry-py` and `postgres-psycopg-py` are repository-owned because
they encode this application's workflow and persistence boundaries. The MAF skill is
grounded in current Microsoft Learn Agent Framework guidance and the installed
`agent-framework-foundry` package; it intentionally does not target
`agent-framework-azure-ai` or `AzureAIAgentsProvider`.
