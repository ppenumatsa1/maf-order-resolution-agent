from __future__ import annotations

import logging
import sys
import types
from typing import Any

import pytest
from app.core import telemetry


@pytest.fixture(autouse=True)
def reset_observability() -> None:
    telemetry._reset_observability_for_tests()


class _FakeProvider:
    def __init__(self, resource: Any | None = None) -> None:
        self.resource = resource
        self.processors: list[Any] = []

    def add_span_processor(self, processor: Any) -> None:
        self.processors.append(processor)


def test_setup_observability_preserves_otlp_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _FakeProvider()
    exporters: list[str] = []
    instrumentation_calls: list[dict[str, Any]] = []

    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://localhost:4318/v1/traces")
    monkeypatch.setattr(telemetry, "TracerProvider", lambda resource=None: provider)
    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", lambda _provider: None)
    monkeypatch.setattr(telemetry.trace, "get_tracer_provider", lambda: provider)
    monkeypatch.setattr(telemetry, "OTLPSpanExporter", lambda endpoint: exporters.append(endpoint))
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", lambda exporter: ("processor", exporter))
    monkeypatch.setattr(
        telemetry,
        "enable_instrumentation",
        lambda **kwargs: instrumentation_calls.append(kwargs),
    )

    status = telemetry.setup_observability()

    assert status.telemetry_enabled is True
    assert status.otlp_configured is True
    assert status.azure_monitor_configured is False
    assert exporters == ["http://localhost:4318/v1/traces"]
    assert provider.processors == [("processor", None)]
    assert instrumentation_calls == [{"enable_sensitive_data": False}]


def test_setup_observability_configures_application_insights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    instrumentation_calls: list[dict[str, Any]] = []
    provider = _FakeProvider()

    azure = types.ModuleType("azure")
    monitor = types.ModuleType("azure.monitor")
    opentelemetry = types.ModuleType("azure.monitor.opentelemetry")

    def configure_azure_monitor(**kwargs: Any) -> None:
        calls.append(kwargs)

    opentelemetry.configure_azure_monitor = configure_azure_monitor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.monitor", monitor)
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", opentelemetry)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=test")
    monkeypatch.setenv("OTEL_RECORD_CONTENT", "true")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.setattr(telemetry.trace, "get_tracer_provider", lambda: provider)
    monkeypatch.setattr(
        telemetry,
        "enable_instrumentation",
        lambda **kwargs: instrumentation_calls.append(kwargs),
    )

    status = telemetry.setup_observability()

    assert status.azure_monitor_configured is True
    assert status.sensitive_content_enabled is True
    assert calls[0]["connection_string"] == "InstrumentationKey=test"
    assert "resource" in calls[0]
    assert instrumentation_calls == [{"enable_sensitive_data": True}]


def test_setup_observability_uses_appinsights_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    instrumentation_calls: list[dict[str, Any]] = []
    provider = _FakeProvider()

    azure = types.ModuleType("azure")
    monitor = types.ModuleType("azure.monitor")
    opentelemetry = types.ModuleType("azure.monitor.opentelemetry")

    def configure_azure_monitor(**kwargs: Any) -> None:
        calls.append(kwargs)

    opentelemetry.configure_azure_monitor = configure_azure_monitor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.monitor", monitor)
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", opentelemetry)
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    monkeypatch.setenv("APPINSIGHTS_CONNECTION_STRING", "InstrumentationKey=alias-test;")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.setattr(telemetry.trace, "get_tracer_provider", lambda: provider)
    monkeypatch.setattr(
        telemetry,
        "enable_instrumentation",
        lambda **kwargs: instrumentation_calls.append(kwargs),
    )

    status = telemetry.setup_observability()

    assert status.azure_monitor_configured is True
    assert calls[0]["connection_string"] == "InstrumentationKey=alias-test"
    assert instrumentation_calls == [{"enable_sensitive_data": False}]


def test_setup_observability_prefers_full_alias_over_compact_canonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    provider = _FakeProvider()

    azure = types.ModuleType("azure")
    monitor = types.ModuleType("azure.monitor")
    opentelemetry = types.ModuleType("azure.monitor.opentelemetry")

    def configure_azure_monitor(**kwargs: Any) -> None:
        calls.append(kwargs)

    opentelemetry.configure_azure_monitor = configure_azure_monitor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.monitor", monitor)
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", opentelemetry)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=compact-only")
    monkeypatch.setenv(
        "APPINSIGHTS_CONNECTION_STRING",
        "InstrumentationKey=full-value;IngestionEndpoint=https://eastus2-3.in.applicationinsights.azure.com/;",
    )
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.setattr(telemetry.trace, "get_tracer_provider", lambda: provider)

    status = telemetry.setup_observability()

    assert status.azure_monitor_configured is True
    assert (
        calls[0]["connection_string"]
        == "InstrumentationKey=full-value;IngestionEndpoint=https://eastus2-3.in.applicationinsights.azure.com/"
    )


def test_setup_observability_degrades_when_application_insights_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    instrumentation_calls: list[dict[str, Any]] = []

    azure = types.ModuleType("azure")
    monitor = types.ModuleType("azure.monitor")
    opentelemetry = types.ModuleType("azure.monitor.opentelemetry")

    def configure_azure_monitor(**_kwargs: Any) -> None:
        raise ValueError("malformed connection string")

    opentelemetry.configure_azure_monitor = configure_azure_monitor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.monitor", monitor)
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", opentelemetry)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "not-a-valid-value")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.setattr(
        telemetry,
        "enable_instrumentation",
        lambda **kwargs: instrumentation_calls.append(kwargs),
    )

    with caplog.at_level(logging.ERROR, logger=telemetry.__name__):
        status = telemetry.setup_observability()

    assert status.telemetry_enabled is True
    assert status.azure_monitor_configured is False
    assert status.instrumentation_enabled is True
    assert instrumentation_calls == [{"enable_sensitive_data": False}]
    assert "Azure Monitor telemetry configuration failed" in caplog.text


def test_setup_observability_degrades_when_instrumentation_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)

    def enable_instrumentation(**_kwargs: Any) -> None:
        raise RuntimeError("instrumentation failed")

    monkeypatch.setattr(telemetry, "enable_instrumentation", enable_instrumentation)

    with caplog.at_level(logging.ERROR, logger=telemetry.__name__):
        status = telemetry.setup_observability()

    assert status.telemetry_enabled is True
    assert status.azure_monitor_configured is False
    assert status.instrumentation_enabled is False
    assert "Agent Framework instrumentation setup failed" in caplog.text


def test_setup_observability_can_disable_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    instrumentation_calls: list[dict[str, Any]] = []
    monkeypatch.setenv("ENABLE_TELEMETRY", "false")
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=test")
    monkeypatch.setattr(
        telemetry,
        "enable_instrumentation",
        lambda **kwargs: instrumentation_calls.append(kwargs),
    )

    status = telemetry.setup_observability()

    assert status.telemetry_enabled is False
    assert status.instrumentation_enabled is False
    assert status.azure_monitor_configured is False
    assert instrumentation_calls == []


def test_business_events_omit_content_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    class FakeSpan:
        def is_recording(self) -> bool:
            return True

        def add_event(self, name: str, attributes: dict[str, Any]) -> None:
            events.append((name, attributes))

    monkeypatch.delenv("OTEL_RECORD_CONTENT", raising=False)
    monkeypatch.setattr(telemetry.trace, "get_current_span", lambda: FakeSpan())

    telemetry.record_business_event(
        "workflow.event",
        {"message": "customer text", "workflow.status": "completed", "count": 1},
    )

    assert events == [("workflow.event", {"workflow.status": "completed", "count": 1})]


def test_safe_attributes_drop_none_and_sensitive_values() -> None:
    assert telemetry._safe_attributes(
        {
            "workflow.status": None,
            "workflow.thread_id": "thread-1",
            "prompt": "customer content",
            "amount": 12.5,
        }
    ) == {"workflow.thread_id": "thread-1", "amount": 12.5}


def test_fastapi_instrumentation_respects_telemetry_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENABLE_TELEMETRY", "false")

    assert telemetry.instrument_fastapi_app(object()) is False


def test_fastapi_instrumentation_excludes_stream_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeFastAPIInstrumentor:
        @staticmethod
        def instrument_app(app: object, **kwargs: Any) -> None:
            calls.append({"app": app, **kwargs})

    fake_module = types.ModuleType("opentelemetry.instrumentation.fastapi")
    fake_module.FastAPIInstrumentor = FakeFastAPIInstrumentor
    monkeypatch.setitem(sys.modules, "opentelemetry.instrumentation.fastapi", fake_module)
    monkeypatch.setenv("ENABLE_TELEMETRY", "true")
    monkeypatch.setenv("ENABLE_INSTRUMENTATION", "true")

    app = object()

    assert telemetry.instrument_fastapi_app(app) is True
    assert calls == [{"app": app, "excluded_urls": r".*/api/chat/stream/.*"}]


def test_observe_maf_workflow_event_records_sample_event_types_without_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    class FakeSpan:
        def is_recording(self) -> bool:
            return True

        def add_event(self, name: str, attributes: dict[str, Any]) -> None:
            events.append((name, attributes))

    class FakeMafEvent:
        def __init__(self, event_type: str) -> None:
            self.type = event_type
            self.executor_id = "triage-agent"
            self.data = "customer order text"

    monkeypatch.delenv("OTEL_RECORD_CONTENT", raising=False)
    monkeypatch.setattr(telemetry.trace, "get_current_span", lambda: FakeSpan())

    for event_type in (
        "executor_invoked",
        "executor_completed",
        "output",
        "message",
        "tool_call",
    ):
        telemetry.observe_maf_workflow_event(
            FakeMafEvent(event_type), workflow_name="order_resolution"
        )

    assert events == [
        (
            "maf.workflow.event",
            {
                "maf.workflow": "order_resolution",
                "maf.event.type": "executor_invoked",
                "maf.executor_id": "triage-agent",
            },
        ),
        (
            "maf.workflow.event",
            {
                "maf.workflow": "order_resolution",
                "maf.event.type": "executor_completed",
                "maf.executor_id": "triage-agent",
            },
        ),
        (
            "maf.workflow.event",
            {
                "maf.workflow": "order_resolution",
                "maf.event.type": "output",
                "maf.executor_id": "triage-agent",
            },
        ),
    ]


def test_observe_maf_workflow_event_records_content_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    class FakeSpan:
        def is_recording(self) -> bool:
            return True

        def add_event(self, name: str, attributes: dict[str, Any]) -> None:
            events.append((name, attributes))

    class FakeMafEvent:
        type = "output"
        executor_id = "resolution-agent"
        data = {"message": "customer order text"}

    monkeypatch.setenv("OTEL_RECORD_CONTENT", "true")
    monkeypatch.setattr(telemetry.trace, "get_current_span", lambda: FakeSpan())

    telemetry.observe_maf_workflow_event(FakeMafEvent(), workflow_name="order_resolution")

    assert events == [
        (
            "maf.workflow.event",
            {
                "maf.workflow": "order_resolution",
                "maf.event.type": "output",
                "maf.executor_id": "resolution-agent",
                "data": "{'message': 'customer order text'}",
            },
        )
    ]
