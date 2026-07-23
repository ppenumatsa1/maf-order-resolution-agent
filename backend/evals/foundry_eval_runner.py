from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from app.maf.clients import get_foundry_models_config
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential

_REQUIRED_CONVERSATION_FIELDS = (
    "low_risk_thread_id",
    "high_risk_thread_id",
    "damaged_item_thread_id",
)
_TERMINAL_EVAL_STATUSES = {"completed", "failed", "canceled"}
_FUTURE_CLOCK_SKEW = timedelta(minutes=5)


def _read_eval_config(path: Path) -> dict[str, object]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("backend/eval.yaml must be a mapping")
    return config


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _to_jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _to_jsonable(value.dict())
    return str(value)


def _parse_utc_timestamp(payload: dict[str, object], field: str) -> datetime:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Hosted E2E evidence is missing {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Hosted E2E evidence {field} must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"Hosted E2E evidence {field} must be UTC")
    return parsed.astimezone(timezone.utc)


def _parse_hosted_e2e_evidence(
    payload: object,
    *,
    max_age_seconds: float,
    now: datetime | None = None,
) -> tuple[datetime, datetime, list[str]]:
    if not isinstance(payload, dict):
        raise ValueError("Hosted E2E evidence must be a JSON object")
    if max_age_seconds <= 0:
        raise ValueError("Hosted E2E evidence max age must be positive")

    started_at = _parse_utc_timestamp(payload, "started_at")
    generated_at = _parse_utc_timestamp(payload, "generated_at")
    if generated_at < started_at:
        raise ValueError("Hosted E2E evidence generated_at cannot precede started_at")

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("Current time used for evidence validation must include a timezone")
    current_time = current_time.astimezone(timezone.utc)
    if started_at > current_time + _FUTURE_CLOCK_SKEW:
        raise ValueError("Hosted E2E evidence started_at is in the future")
    if generated_at > current_time + _FUTURE_CLOCK_SKEW:
        raise ValueError("Hosted E2E evidence generated_at is in the future")
    if current_time - started_at > timedelta(seconds=max_age_seconds):
        raise ValueError(
            f"Hosted E2E evidence is stale; started_at exceeds {max_age_seconds:g} seconds"
        )

    conversation_ids: list[str] = []
    for field in _REQUIRED_CONVERSATION_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError(f"Hosted E2E evidence requires non-empty {field}")
        conversation_ids.append(value)
    if len(set(conversation_ids)) != len(conversation_ids):
        raise ValueError("Hosted E2E evidence scenario conversation IDs must be unique")
    return started_at, generated_at, conversation_ids


def _load_hosted_e2e_evidence(
    path: Path,
    *,
    max_age_seconds: float,
    now: datetime | None = None,
) -> tuple[datetime, datetime, list[str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Hosted E2E evidence is required: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Hosted E2E evidence must be valid JSON") from exc
    return _parse_hosted_e2e_evidence(
        payload,
        max_age_seconds=max_age_seconds,
        now=now,
    )


def _build_conversation_trace_testing_criteria(
    evaluators: list[str],
    judge_model: str,
) -> list[dict[str, object]]:
    return [
        {
            "type": "azure_ai_evaluator",
            "name": evaluator_name,
            "evaluator_name": f"builtin.{evaluator_name}",
            "initialization_parameters": {"model": judge_model},
            "data_mapping": {"messages": "{{item.messages}}"},
        }
        for evaluator_name in evaluators
    ]


def _build_conversation_trace_run(
    conversation_ids: list[str],
) -> dict[str, object]:
    return {
        "data_source": {
            "type": "azure_ai_trace_data_source_preview",
            "trace_source": {
                "type": "conversation_id_source",
                "conversation_ids": conversation_ids,
            },
        },
        "extra_body": {"evaluation_level": "conversation"},
    }


async def run_foundry_eval() -> None:
    root = Path(__file__).resolve().parents[1]
    foundry_root = root / ".foundry"
    config = _read_eval_config(root / "eval.yaml")
    foundry_cfg = config.get("foundry")
    if not isinstance(foundry_cfg, dict):
        raise ValueError("backend/eval.yaml is missing foundry config block")
    trace_cfg = foundry_cfg.get("trace_evaluation")
    if not isinstance(trace_cfg, dict):
        raise ValueError("backend/eval.yaml is missing foundry.trace_evaluation")
    evidence_uri = trace_cfg.get("evidence_file")
    if not isinstance(evidence_uri, str) or not evidence_uri:
        raise ValueError("backend/eval.yaml trace_evaluation.evidence_file is required")
    max_traces = int(trace_cfg.get("max_traces", 10))
    if max_traces < len(_REQUIRED_CONVERSATION_FIELDS):
        raise ValueError(
            "backend/eval.yaml trace_evaluation.max_traces must cover all required scenarios"
        )
    max_evidence_age = float(trace_cfg.get("max_evidence_age_seconds", 21600))

    evaluator_values = foundry_cfg.get("evaluators")
    if not isinstance(evaluator_values, list) or not all(
        isinstance(value, str) and value for value in evaluator_values
    ):
        raise ValueError("backend/eval.yaml foundry.evaluators must be a list of evaluator names")
    evaluators = _dedupe([str(value) for value in evaluator_values])
    eval_name = str(foundry_cfg.get("name", "order-resolution-foundry-report"))
    poll_interval = float(
        os.getenv("FOUNDRY_EVAL_POLL_INTERVAL", foundry_cfg.get("poll_interval", 5))
    )
    timeout = float(os.getenv("FOUNDRY_EVAL_TIMEOUT", foundry_cfg.get("timeout", 900)))

    evidence_path = root / evidence_uri
    started_at, generated_at, conversation_ids = _load_hosted_e2e_evidence(
        evidence_path,
        max_age_seconds=max_evidence_age,
    )
    report_path = foundry_root / "results" / "foundry-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "status": "failed",
        "provider": "foundry-trace",
        "evaluators": evaluators,
        "conversation_ids": conversation_ids,
        "e2e_started_at": started_at.isoformat(),
        "e2e_generated_at": generated_at.isoformat(),
    }

    try:
        models_cfg = get_foundry_models_config()
        if models_cfg is None:
            raise RuntimeError(
                "Foundry model configuration is missing. Set FOUNDRY_PROJECTS_ENDPOINT and "
                "FOUNDRY_MODEL_DEPLOYMENT_NAME."
            )
        judge_model = os.getenv("FOUNDRY_EVAL_MODEL", models_cfg.model)
        async with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                endpoint=models_cfg.project_endpoint,
                credential=credential,
            ) as project_client,
            project_client.get_openai_client() as openai_client,
        ):
            eval_object = await openai_client.evals.create(
                name=f"{eval_name}-trace",
                data_source_config={"type": "azure_ai_source", "scenario": "traces"},
                testing_criteria=_build_conversation_trace_testing_criteria(
                    evaluators,
                    judge_model,
                ),
            )
            eval_run = await openai_client.evals.runs.create(
                eval_id=eval_object.id,
                name=f"{eval_name} trace run",
                metadata={
                    "e2e_started_at": started_at.isoformat(),
                    "e2e_generated_at": generated_at.isoformat(),
                    "conversation_count": str(len(conversation_ids)),
                },
                **_build_conversation_trace_run(conversation_ids),
            )
            start = asyncio.get_running_loop().time()
            while str(eval_run.status) not in _TERMINAL_EVAL_STATUSES:
                if asyncio.get_running_loop().time() - start > timeout:
                    await openai_client.evals.runs.cancel(
                        run_id=eval_run.id,
                        eval_id=eval_object.id,
                    )
                    raise TimeoutError(
                        f"Foundry trace evaluation timed out after {timeout} seconds"
                    )
                await asyncio.sleep(poll_interval)
                eval_run = await openai_client.evals.runs.retrieve(
                    run_id=eval_run.id,
                    eval_id=eval_object.id,
                )
        payload = {
            "status": str(eval_run.status),
            "provider": "foundry-trace",
            "eval_id": eval_object.id,
            "run_id": eval_run.id,
            "conversation_count": len(conversation_ids),
            "evaluators": evaluators,
            "conversation_ids": conversation_ids,
            "e2e_started_at": started_at.isoformat(),
            "e2e_generated_at": generated_at.isoformat(),
            "result_counts": _to_jsonable(getattr(eval_run, "result_counts", None)),
            "report_url": (
                f"{models_cfg.project_endpoint.rstrip('/')}/evaluation/evaluations/"
                f"{eval_object.id}/runs/{eval_run.id}"
            ),
            "error": _to_jsonable(getattr(eval_run, "error", None)),
        }
    except Exception as exc:  # noqa: BLE001
        payload["status"] = "timeout" if isinstance(exc, TimeoutError) else "failed"
        payload["error"] = str(exc)
        if "eval_object" in locals():
            payload["eval_id"] = getattr(eval_object, "id", None)
        if "eval_run" in locals():
            payload["run_id"] = getattr(eval_run, "id", None)
            payload["run_status"] = str(getattr(eval_run, "status", "unknown"))
        if payload.get("eval_id") and payload.get("run_id") and "models_cfg" in locals():
            payload["report_url"] = (
                f"{models_cfg.project_endpoint.rstrip('/')}/evaluation/evaluations/"
                f"{payload['eval_id']}/runs/{payload['run_id']}"
            )
    report_path.write_text(json.dumps(_to_jsonable(payload), indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"Foundry report saved to: {report_path}")

    enforce_pass = os.getenv("FOUNDRY_EVAL_ENFORCE_PASS", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    if enforce_pass and str(payload.get("status")) != "completed":
        raise RuntimeError(f"Foundry trace eval run ended with status: {payload.get('status')}")

    max_errored = os.getenv("FOUNDRY_EVAL_MAX_ERRORED")
    result_counts = payload.get("result_counts")
    if max_errored is not None and isinstance(result_counts, dict):
        errored = int(result_counts.get("errored", 0))
        if errored > int(max_errored):
            raise RuntimeError(
                f"Foundry trace eval produced {errored} errored items; maximum is {max_errored}"
            )


if __name__ == "__main__":
    asyncio.run(run_foundry_eval())
