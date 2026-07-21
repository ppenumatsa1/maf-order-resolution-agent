# Infrastructure Scaffolding

This directory contains the one Azure app-hosted deployment package.

- `azure-apphosted/`: two public Container Apps, one ACR, Entra-only Azure
  PostgreSQL, Application Insights, Log Analytics, and a Foundry
  models/evaluations module in one resource group.

The FastAPI/MAF backend is the only application host; Foundry is not a hosted
agent runtime.
