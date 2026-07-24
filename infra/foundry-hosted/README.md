# Public Foundry Hosted Agent

`infra/foundry-hosted` is the only Azure deployment path in this branch. It
deploys the shared MAF workflow as a public Foundry Responses agent, an external
React frontend Container App, and an internal FastAPI Responses-wrapper
Container App.

## What Bicep manages

- The existing public Foundry account, ACR, Log Analytics, and Application
  Insights component are referenced in the named public development resource
  group.
- The template creates the `order-resolution-public-managed-dev2` project with
  Microsoft-managed agent state and its system-assigned identity.
- A project-scoped `ApplicationInsights` connection is created with the
  configured component as its target. This connection is required by Foundry
  trace evaluation; runtime environment variables alone are insufficient.
- Public PostgreSQL Flexible Server, `maf_workflow` database, TLS, and the
  Azure-services firewall rule.
- An external frontend Container App and an internal backend Container App. The
  frontend proxies browser `/api` calls to the backend; the backend's
  system-assigned managed identity has the project-scoped Foundry role required
  to invoke Responses.
- A dedicated Standard LRS Blob Storage account for Foundry evaluation
  artifacts only. It has no workflow, session, vector, or runtime data.
  Foundry connects through an Entra ID account connection, which materializes
  the project connection; only the Foundry account and project managed identities have `Storage Blob Data
  Owner` on that account, as required by the Foundry evaluator.
- A dedicated `gpt-4o-mini-evaluation` deployment with 10K TPM capacity. It
  is used only as the Foundry trace-evaluation judge, preventing the evaluator
  from competing with the hosted agent's 1K TPM chat deployment.
- Foundry User assignments for the project identity and optional Log Analytics
  Reader assignments for the release operator.

Foundry supplies and operates the agent session, file, and vector-store services.
This deployment manages no customer-owned service for those capabilities.

There are no customer-managed networking or runner resources.

The public frontend URL is
`https://ora-public-dev2-frontend.greentree-dc9ce897.eastus2.azurecontainerapps.io/`.
The backend FQDN is internal by design and must not be used as a browser API
base URL.

## Public target

- Resource group: `rg-maf-ora-foundry-public-dev2`
- azd environment: `foundry-public-dev2`
- Project: `order-resolution-public-managed-dev2`
- Agent: `order-resolution-hosted`

## Authenticated local release

```bash
AZURE_SUBSCRIPTION_ID="<subscription-id>" \
RUNTIME_DATABASE_URL="postgresql://<user>:<password>@<server>.postgres.database.azure.com:5432/maf_workflow?sslmode=require" \
POSTGRES_ADMIN_PASSWORD="<postgres-admin-password>" \
make foundry-release
```

The release script validates local gates, executes `azd up --no-prompt`, invokes
the hosted agent for low-risk and HITL cases, runs the enforced Foundry
evaluation, and waits for Application Insights telemetry. Follow it with hosted
browser validation:

```bash
PLAYWRIGHT_BASE_URL="https://ora-public-dev2-frontend.greentree-dc9ce897.eastus2.azurecontainerapps.io" \
make test-e2e
```

## Foundry evaluation configuration

From the repository root, `make eval-foundry` resolves its evaluator endpoint
and deployment names through this nested AZD project's selected environment.
It uses an allow-list of non-secret values and does not source or display the
environment `.env` file. Check resolution without contacting Foundry:

```bash
make eval-foundry-config
```

To evaluate against another existing local environment without running
`azd env select`, use:

```bash
FOUNDRY_AZD_ENV_NAME=<environment> make eval-foundry
```

`make foundry-up` verifies the deployed project still has an
`ApplicationInsights` connection targeting the configured component. It fails
before hosted E2E/evaluation if that prerequisite is absent or drifted.

The authenticated release script assigns its signed-in Entra user `Log Analytics
Reader` on the configured Application Insights component and linked workspace so
that Foundry trace views can load. Set `FOUNDRY_TRACE_READER_PRINCIPAL_ID` to
grant that view permission to a different user.

For an infrastructure-only PostgreSQL check:

```bash
AZURE_SUBSCRIPTION_ID="<subscription-id>" make foundry-postgres-readiness
```

Compile before a deployment:

```bash
az bicep build --file infra/foundry-hosted/iac/main.bicep
```
