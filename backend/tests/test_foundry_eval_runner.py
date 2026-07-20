from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from evals.foundry_eval_runner import (
    _build_conversation_trace_testing_criteria,
    _load_hosted_e2e_evidence,
)


def test_load_hosted_e2e_evidence_requires_low_risk_and_approved_conversations(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "hosted-e2e-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-20T14:00:00Z",
                "started_at": "2026-07-20T13:45:00Z",
                "low_risk_thread_id": "conv-low",
                "approved_thread_id": "conv-approved",
            }
        ),
        encoding="utf-8",
    )

    started_at, conversation_ids = _load_hosted_e2e_evidence(evidence)

    assert started_at == datetime(2026, 7, 20, 13, 45, tzinfo=timezone.utc)
    assert conversation_ids == ["conv-low", "conv-approved"]


def test_load_hosted_e2e_evidence_rejects_missing_conversation(tmp_path: Path) -> None:
    evidence = tmp_path / "hosted-e2e-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-20T14:00:00Z",
                "low_risk_thread_id": "conv-low",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="two conversation IDs"):
        _load_hosted_e2e_evidence(evidence)


def test_conversation_trace_criteria_use_messages_mapping() -> None:
    criteria = _build_conversation_trace_testing_criteria(["coherence"], "gpt-4o-mini")

    assert criteria == [
        {
            "type": "azure_ai_evaluator",
            "name": "coherence",
            "evaluator_name": "builtin.coherence",
            "initialization_parameters": {"model": "gpt-4o-mini"},
            "data_mapping": {
                "messages": "{{item.messages}}",
            },
        }
    ]
