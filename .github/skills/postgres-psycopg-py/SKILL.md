---
name: postgres-psycopg-py
description: Maintain PostgreSQL persistence with Psycopg v3 and psycopg_pool in this Python workflow service. Use for DATABASE_URL, connection pools, repository adapters, schema changes, pgvector, Azure Database for PostgreSQL Flexible Server, transactions, and idempotent database writes.
---

# PostgreSQL and Psycopg for Order Resolution

Use this skill for the repository's durable PostgreSQL path. PostgreSQL stores workflow runs,
events, conversation messages, checkpoints, approvals, sessions, and evaluation records.

## Ownership and configuration

- `backend/app/core/database.py` owns the shared `PostgresDatabase` pool and `DATABASE_URL`
  configuration.
- `backend/app/infrastructure/persistence/*` owns storage adapters. Keep route, service, MAF
  runtime, and persistence responsibilities separated.
- The public Foundry/Container Apps path uses `STORE_PROVIDER=postgres`; Azure
  Database for PostgreSQL is selected through `DATABASE_URL`.
- PostgreSQL is limited to workflow audit/control-plane persistence; do not add
  vector, document, or retrieval stores to it.

## Safe persistence patterns

- Reuse the shared `psycopg_pool.ConnectionPool`; never create a pool per request, workflow
  executor, or repository method.
- Use parameterized SQL (`cursor.execute(sql, parameters)`) for every dynamic value. Do not
  interpolate values into SQL strings.
- Keep schema changes in `backend/app/sql/schema.sql`, make initialization safe to repeat, and
  update repository code and tests together.
- Give every side-effecting write an idempotency key and preserve existing retry behavior. Do
  not blindly retry writes after an uncertain connection or transaction outcome.
- Surface database failures through the application's established error and telemetry paths; do
  not hide them with broad exception handling or success-shaped fallback values.
- Use explicit transaction boundaries when an operation must commit multiple changes
  atomically. Do not change the configured autocommit behavior without reviewing all affected
  repository methods.

## Azure Database for PostgreSQL

- Prefer Microsoft Entra authentication and managed identity when the Azure deployment's
  database and RBAC configuration support it. Require TLS for hosted connections.
- Keep credentials and connection strings in environment/secret configuration, never in source
  code or logs.
- Preserve the existing Azure deployment boundary: Bicep provisions the server and application
  configuration provides `DATABASE_URL`; backend persistence code remains provider-neutral.

## Dynamic guidance

Use first-party documentation for service configuration that changes over time:

| Need | Lookup |
|---|---|
| Python connection and Entra authentication | `microsoft_docs_search(query="Azure Database for PostgreSQL Flexible Server Python psycopg Microsoft Entra authentication")` |
| Networking and TLS | `microsoft_docs_search(query="Azure Database for PostgreSQL Flexible Server networking TLS")` |
| Azure PostgreSQL limits and maintenance | `microsoft_docs_search(query="Azure Database for PostgreSQL Flexible Server limits maintenance")` |
