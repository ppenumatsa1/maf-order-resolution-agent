from __future__ import annotations

import json
from pathlib import Path

import pytest
from evals.foundry_eval_runner import _load_report_queries


def test_load_report_queries_selects_configured_canonical_cases(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        "\n".join(
            [
                json.dumps({"id": "low", "input": "Low-risk request"}),
                json.dumps({"id": "high", "input": "High-risk request"}),
            ]
        ),
        encoding="utf-8",
    )

    assert _load_report_queries(dataset, ["low", "high"]) == [
        "Low-risk request",
        "High-risk request",
    ]


def test_load_report_queries_rejects_missing_configured_case(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(json.dumps({"id": "low", "input": "Low-risk request"}), encoding="utf-8")

    with pytest.raises(ValueError, match="missing from"):
        _load_report_queries(dataset, ["high"])
