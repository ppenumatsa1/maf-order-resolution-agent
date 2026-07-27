# Tech Stack

## Application

- Python, FastAPI, Uvicorn, and Pydantic v2
- Microsoft Agent Framework (MAF) workflow runtime
- React, Vite, and TypeScript
- PostgreSQL with Psycopg for durable workflow state
- MCP over streamable HTTP for optional integration
- OpenTelemetry and Application Insights

## Azure target

- Azure Container Apps for the frontend and FastAPI application
- Azure Container Registry, Log Analytics, and Application Insights
- Azure Database for PostgreSQL Flexible Server with managed-identity Entra
  authentication
- Foundry model deployments for inference and report-only evaluation only

## Skills

Use task-specific repository skills. `agent-framework-foundry-py` covers the
model client and MAF workflow integration; `azure-ai-projects-py` covers model
deployments and evaluations. Neither authorizes a Foundry application host.
