from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from evals.foundry_eval_runner import (
    _TERMINAL_EVAL_STATUSES,
    _build_conversation_trace_run,
    _build_conversation_trace_testing_criteria,
    _load_hosted_e2e_evidence,
    _parse_hosted_e2e_evidence,
)

_NOW = datetime(2026, 7, 23, 15, 0, tzinfo=timezone.utc)


def _valid_evidence() -> dict[str, object]:
    return {
        "generated_at": "2026-07-23T14:50:00Z",
        "started_at": "2026-07-23T14:45:00Z",
        "base_id": "foundry-e2e-test",
        "low_risk_thread_id": "conv-low",
        "high_risk_thread_id": "conv-high",
        "damaged_item_thread_id": "conv-damaged",
    }


def test_parse_hosted_e2e_evidence_returns_all_scenario_conversations() -> None:
    started_at, generated_at, conversation_ids = _parse_hosted_e2e_evidence(
        _valid_evidence(),
        max_age_seconds=3600,
        now=_NOW,
    )

    assert started_at == datetime(2026, 7, 23, 14, 45, tzinfo=timezone.utc)
    assert generated_at == datetime(2026, 7, 23, 14, 50, tzinfo=timezone.utc)
    assert conversation_ids == ["conv-low", "conv-high", "conv-damaged"]


@pytest.mark.parametrize(
    "missing_field",
    [
        "low_risk_thread_id",
        "high_risk_thread_id",
        "damaged_item_thread_id",
    ],
)
def test_parse_hosted_e2e_evidence_requires_each_scenario_id(missing_field: str) -> None:
    evidence = _valid_evidence()
    del evidence[missing_field]

    with pytest.raises(ValueError, match=missing_field):
        _parse_hosted_e2e_evidence(
            evidence,
            max_age_seconds=3600,
            now=_NOW,
        )


def test_parse_hosted_e2e_evidence_rejects_duplicate_scenario_ids() -> None:
    evidence = _valid_evidence()
    evidence["damaged_item_thread_id"] = evidence["high_risk_thread_id"]

    with pytest.raises(ValueError, match="must be unique"):
        _parse_hosted_e2e_evidence(
            evidence,
            max_age_seconds=3600,
            now=_NOW,
        )


def test_parse_hosted_e2e_evidence_rejects_non_utc_timestamps() -> None:
    evidence = _valid_evidence()
    evidence["generated_at"] = "2026-07-23T09:50:00-05:00"

    with pytest.raises(ValueError, match="generated_at must be UTC"):
        _parse_hosted_e2e_evidence(
            evidence,
            max_age_seconds=3600,
            now=_NOW,
        )


def test_parse_hosted_e2e_evidence_rejects_stale_evidence() -> None:
    evidence = _valid_evidence()
    evidence["started_at"] = "2026-07-23T12:00:00Z"

    with pytest.raises(ValueError, match="is stale"):
        _parse_hosted_e2e_evidence(
            evidence,
            max_age_seconds=3600,
            now=_NOW,
        )


def test_load_hosted_e2e_evidence_rejects_missing_file() -> None:
    evidence_path = Path("backend/.foundry/results/does-not-exist.json")

    with pytest.raises(FileNotFoundError, match="Hosted E2E evidence is required"):
        _load_hosted_e2e_evidence(
            evidence_path,
            max_age_seconds=3600,
            now=_NOW,
        )


def test_load_hosted_e2e_evidence_rejects_malformed_json() -> None:
    evidence_path = Path("backend/.foundry/results/hosted-e2e-evidence.json")

    with (
        patch.object(Path, "is_file", return_value=True),
        patch.object(Path, "read_text", return_value="{not-json"),
        pytest.raises(ValueError, match="must be valid JSON"),
    ):
        _load_hosted_e2e_evidence(
            evidence_path,
            max_age_seconds=3600,
            now=_NOW,
        )


def test_conversation_trace_criteria_use_messages_mapping() -> None:
    criteria = _build_conversation_trace_testing_criteria(["coherence"], "gpt-4o-mini")

    assert criteria == [
        {
            "type": "azure_ai_evaluator",
            "name": "coherence",
            "evaluator_name": "builtin.coherence",
            "initialization_parameters": {"model": "gpt-4o-mini"},
            "data_mapping": {"messages": "{{item.messages}}"},
        }
    ]


def test_trace_run_reuses_exact_conversations_at_conversation_level() -> None:
    conversation_ids = ["conv-low", "conv-high", "conv-damaged"]

    trace_run = _build_conversation_trace_run(conversation_ids)

    assert trace_run == {
        "data_source": {
            "type": "azure_ai_trace_data_source_preview",
            "trace_source": {
                "type": "conversation_id_source",
                "conversation_ids": conversation_ids,
            },
        },
        "extra_body": {"evaluation_level": "conversation"},
    }
    assert "target" not in trace_run["data_source"]


def test_terminal_eval_statuses_use_openai_canceled_spelling() -> None:
    assert "canceled" in _TERMINAL_EVAL_STATUSES
    assert "cancelled" not in _TERMINAL_EVAL_STATUSES
