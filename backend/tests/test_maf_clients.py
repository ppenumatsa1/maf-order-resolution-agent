from __future__ import annotations

import pytest
from app.maf import clients
from app.maf.workflows import order_resolution as workflow_module
from workflows.maf_sdk_workflow import MafSdkSequentialWorkflow


@pytest.fixture(autouse=True)
def clear_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MAF_PROVIDER",
        "MAF_MODEL",
        "FOUNDRY_PROJECTS_ENDPOINT",
        "FOUNDRY_PROJECT_ENDPOINT",
        "FOUNDRY_MODEL_DEPLOYMENT_NAME",
        "FOUNDRY_MODEL",
        "OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_foundry_models_config_requires_project_endpoint_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "FOUNDRY_PROJECTS_ENDPOINT", "https://example.services.ai.azure.com/api/projects/p"
    )

    assert clients.get_foundry_models_config() is None
    assert clients.has_llm_configuration() is False
    assert clients.triage_mode_metadata() == {
        "provider": "deterministic",
        "mode": "local_fallback",
    }


def test_no_foundry_config_uses_deterministic_triage_metadata() -> None:
    assert clients.get_foundry_models_config() is None
    assert clients.has_llm_configuration() is False
    assert clients.triage_mode_metadata() == {
        "provider": "deterministic",
        "mode": "local_fallback",
    }


def test_foundry_models_config_uses_project_first_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "FOUNDRY_PROJECTS_ENDPOINT", "https://example.services.ai.azure.com/api/projects/p"
    )
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini")

    config = clients.get_foundry_models_config()

    assert config is not None
    assert config.project_endpoint == "https://example.services.ai.azure.com/api/projects/p"
    assert config.model == "gpt-4.1-mini"
    assert clients.has_llm_configuration() is True
    assert clients.triage_mode_metadata(config) == {
        "provider": "foundry",
        "mode": "foundry_models",
        "model": "gpt-4.1-mini",
    }


def test_foundry_models_config_prefers_canonical_env_over_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "FOUNDRY_PROJECTS_ENDPOINT",
        "https://canonical.services.ai.azure.com/api/projects/p",
    )
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://legacy.services.ai.azure.com/api/projects/p",
    )
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "canonical-model")
    monkeypatch.setenv("MAF_MODEL", "legacy-model")

    config = clients.get_foundry_models_config()

    assert config is not None
    assert config.project_endpoint == "https://canonical.services.ai.azure.com/api/projects/p"
    assert config.model == "canonical-model"


def test_foundry_models_config_supports_maf_model_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAF_PROVIDER", "foundry_models")
    monkeypatch.setenv(
        "FOUNDRY_PROJECTS_ENDPOINT", "https://example.services.ai.azure.com/api/projects/p"
    )
    monkeypatch.setenv("MAF_MODEL", "configured-model")

    config = clients.get_foundry_models_config()

    assert config is not None
    assert config.provider == "foundry_models"
    assert config.model == "configured-model"


@pytest.mark.asyncio
async def test_workflow_uses_deterministic_triage_without_model_env() -> None:
    workflow = MafSdkSequentialWorkflow.__new__(MafSdkSequentialWorkflow)

    result = await workflow._run_maf_sequence("Order ORD-1001 is late", "no prior context")

    assert result == "triage_summary: order_id=ord-1001; issue_type=late_delivery"


@pytest.mark.asyncio
async def test_workflow_uses_foundry_agents_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    credential_closed = {"value": False}

    class DummyClient:
        def as_agent(self, **kwargs: object) -> str:
            calls.append(kwargs)
            return str(kwargs["name"])

    class DummyCredential:
        async def close(self) -> None:
            credential_closed["value"] = True

    class DummyEvent:
        type = "output"
        data = "foundry triage"

    class DummyStream:
        def __init__(self) -> None:
            self._sent = False

        def __aiter__(self) -> DummyStream:
            return self

        async def __anext__(self) -> DummyEvent:
            if self._sent:
                raise StopAsyncIteration
            self._sent = True
            return DummyEvent()

        async def get_final_response(self) -> object:
            raise AssertionError("streamed output should be used")

    class DummyWorkflow:
        def run(self, *, message: str, stream: bool = False) -> DummyStream:
            assert stream is True
            assert "request:" in message
            return DummyStream()

    class DummySequentialBuilder:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["participants"] == ["TriageAgent", "PolicyAgent", "ResolutionAgent"]
            assert kwargs["intermediate_output_from"] == ["TriageAgent", "PolicyAgent"]

        def build(self) -> DummyWorkflow:
            return DummyWorkflow()

    config = clients.FoundryModelsConfig(
        project_endpoint="https://example.services.ai.azure.com/api/projects/p",
        model="gpt-4.1-mini",
    )
    monkeypatch.setattr(workflow_module, "get_foundry_models_config", lambda: config)
    monkeypatch.setattr(
        workflow_module,
        "create_foundry_chat_client",
        lambda _config: (DummyClient(), DummyCredential(), config),
    )

    workflow = MafSdkSequentialWorkflow.__new__(MafSdkSequentialWorkflow)
    workflow._SequentialBuilder = DummySequentialBuilder

    result = await workflow._run_maf_sequence("Order ORD-1001 is late", "no prior context")

    assert result == "foundry triage"
    assert credential_closed["value"] is True
    assert [call["name"] for call in calls] == ["TriageAgent", "PolicyAgent", "ResolutionAgent"]
    assert all(call["default_options"] == {"store": False} for call in calls)
