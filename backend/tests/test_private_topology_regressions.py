from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.api.v1.routers import chat
from app.modules.order_resolution.models import WorkflowEvent

ROOT = Path(__file__).parents[2]


class _PersistedEventRepository:
    def __init__(self, events: list[WorkflowEvent]) -> None:
        self.events = events
        self.calls: list[tuple[str, int, str | None]] = []

    def list_workflow_events(
        self, thread_id: str, *, limit: int, cursor: str | None
    ) -> tuple[list[WorkflowEvent], str | None, bool]:
        self.calls.append((thread_id, limit, cursor))
        return self.events, None, False


@pytest.mark.asyncio
async def test_responses_wrapper_streams_persisted_native_and_rich_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = WorkflowEvent(
        id="11111111-1111-1111-1111-111111111111",
        type="workflow.output",
        thread_id="thread-private",
        timestamp="2026-07-24T00:00:00+00:00",
        payload={"workflow_run_id": "run-private", "status": "completed", "message": "done"},
    )
    repository = _PersistedEventRepository([event])
    monkeypatch.setattr(chat, "workflow_run_repository", repository)
    monkeypatch.setattr(chat, "config", SimpleNamespace(runtime_target="responses_wrapper"))

    native_response = await chat.stream_chat("thread-private")
    try:
        native_chunk = await anext(native_response.body_iterator)
    finally:
        await native_response.body_iterator.aclose()

    assert native_response.media_type == "text/event-stream"
    assert native_chunk.startswith("data: ")
    assert json.loads(native_chunk.removeprefix("data: ").strip()) == event.model_dump()
    assert repository.calls == [("thread-private", 100, None)]

    rich_stream = chat._persisted_sse_stream("thread-private", rich=True)
    try:
        rich_chunk = await anext(rich_stream)
    finally:
        await rich_stream.aclose()

    rich_envelope = json.loads(rich_chunk.split("data: ", 1)[1].strip())
    assert rich_chunk.startswith("event: workflow.rich\n")
    assert rich_envelope["native_event"] == event.model_dump()
    assert rich_envelope["events"][0]["type"] == "RUN_STARTED"
    assert rich_envelope["events"][-1]["type"] == "RUN_FINISHED"


def test_frontend_uses_same_origin_proxy_without_browser_secrets() -> None:
    frontend = ROOT / "frontend"
    config = (frontend / "src/config.ts").read_text()
    nginx = (frontend / "nginx.conf").read_text()
    entrypoint = (frontend / "docker-entrypoint.sh").read_text()
    public_config = (frontend / "public/env-config.template.js").read_text()

    assert 'return "";' in config
    assert "location ^~ /api/" in nginx
    assert "proxy_pass ${NGINX_API_UPSTREAM};" in nginx
    assert 'proxy_set_header Authorization "";' in nginx
    assert 'proxy_set_header Cookie "";' in nginx
    assert "NGINX_API_UPSTREAM must be set to the internal backend URL" in entrypoint
    assert public_config.strip() == "window.__APP_CONFIG__ = {};"

    browser_sources = "\n".join(
        path.read_text()
        for path in frontend.rglob("*")
        if path.is_file() and "node_modules" not in path.parts
    )
    for secret_name in (
        "FOUNDRY_RESPONSES_ENDPOINT",
        "DATABASE_URL",
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "APPINSIGHTS_CONNECTION_STRING",
    ):
        assert secret_name not in browser_sources


def test_private_aca_topology_keeps_ingress_identity_dns_and_postgres_guardrails() -> None:
    bicep = (ROOT / "infra/foundry-hosted/iac/main.bicep").read_text()
    private_dns = (ROOT / "infra/foundry-hosted/iac/modules/private-dns.bicep").read_text()
    private_endpoint = (
        ROOT / "infra/foundry-hosted/iac/modules/private-endpoint.bicep"
    ).read_text()

    backend = bicep.split("resource backendContainerApp ", 1)[1].split(
        "resource backendContainerAppFoundryUserRoleAssignment ", 1
    )[0]
    frontend = bicep.split("resource frontendContainerApp ", 1)[1].split(
        "output foundryAccountName", 1
    )[0]

    assert "@allowed([\n  'private'\n])" in bicep
    assert "publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled'" in bicep
    assert "module postgresPrivateEndpoint " in bicep
    assert "groupIds: [\n      'postgresqlServer'\n    ]" in bicep
    assert "privatelink.postgres.database.azure.com" in bicep
    assert "createPostgresAzureServicesFirewall bool" in bicep
    assert "resource backendContainerAppFoundryUserRoleAssignment " in bicep
    assert "principalId: backendContainerApp!.identity.principalId" in bicep
    assert "type: 'SystemAssigned, UserAssigned'" in backend
    assert "external: false" in backend
    assert "name: 'DATABASE_URL'\n              secretRef: 'database-url'" in backend
    assert "name: 'FOUNDRY_RESPONSES_ENDPOINT'" in backend
    assert "external: true" in frontend
    assert (
        "value: 'https://${backendContainerApp!.properties.configuration.ingress.fqdn}'" in frontend
    )
    assert "registrationEnabled: false" in private_dns
    assert (
        "privateEndpointNetworkPolicies: 'Disabled'"
        in (ROOT / "infra/foundry-hosted/iac/modules/vnet.bicep").read_text()
    )
    assert "privateDnsZoneId: zoneId" in private_endpoint
