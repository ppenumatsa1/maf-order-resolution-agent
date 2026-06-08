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

- Local JSON file storage for memory and checkpoints (v1)
- Cosmos-compatible abstraction planned for checkpoint and conversation persistence

## Integration

- MCP via streamable HTTP endpoint (`MCP_SERVER_URL`)
- OTEL exporters configurable by environment variables
- App Insights enabled by setting OTLP endpoint to Azure Monitor/OpenTelemetry collector
