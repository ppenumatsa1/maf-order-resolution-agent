# Infrastructure

The only Azure deployment path is
[Foundry hosted](foundry-hosted/README.md). It provisions the public Foundry
project and shared observability/data dependencies, deploys an external frontend
Container App and an internal FastAPI wrapper Container App, and hosts the
Responses-native MAF agent.

Browser traffic is same-origin through the frontend's `/api` proxy. The internal
backend uses managed identity to call Foundry and shares PostgreSQL durable
workflow state with the hosted agent. Local Docker remains the API/SSE/UI
development environment.
