# Tech Stack

## Backend

- Python 3.10+
- FastAPI + Uvicorn
- Pydantic v2
- httpx for MCP HTTP tool calls
- OpenTelemetry SDK + OTLP exporter

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
- App Insights enabled by setting OTLP endpoint to Azure Monitor/OpenTelemetry collector
