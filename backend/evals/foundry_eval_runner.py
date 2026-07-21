from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import yaml
from app.maf.clients import get_foundry_models_config
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential


def _read_eval_config(path: Path) -> dict[str, object]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("backend/eval.yaml must be a mapping")
    return config


def _load_report_queries(dataset_path: Path, case_ids: list[str]) -> list[str]:
    queries_by_case_id: dict[str, str] = {}
    for line_number, line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        row = json.loads(line)
        case_id = row.get("id")
        query = row.get("input")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"{dataset_path}:{line_number} must contain a non-empty id")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"{dataset_path}:{line_number} must contain a non-empty input")
        queries_by_case_id[case_id] = query.strip()

    missing_case_ids = [case_id for case_id in case_ids if case_id not in queries_by_case_id]
    if missing_case_ids:
        raise ValueError(
            f"Foundry report case IDs are missing from {dataset_path}: {', '.join(missing_case_ids)}"
        )
    return [queries_by_case_id[case_id] for case_id in case_ids]


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


async def _capture_app_outputs(queries: list[str], api_url: str) -> list[dict[str, str]]:
    captures: list[dict[str, str]] = []
    async with httpx.AsyncClient(base_url=api_url.rstrip("/"), timeout=90.0) as client:
        for query in queries:
            run = (
                (
                    await client.post(
                        "/api/chat/run",
                        json={
                            "message": query,
                            "customer_id": "foundry-evaluation",
                            "session_id": f"foundry-eval-{uuid4()}",
                        },
                    )
                )
                .raise_for_status()
                .json()
            )
            thread_id = str(run["thread_id"])
            for _ in range(90):
                details = (
                    (await client.get(f"/api/workflows/{thread_id}")).raise_for_status().json()
                )
                if details.get("status") == "waiting_approval":
                    pending = details.get("pending_approvals") or []
                    if not pending:
                        raise RuntimeError(
                            f"Workflow {thread_id} is waiting without an approval request."
                        )
                    (
                        await client.post(
                            "/api/hitl/respond",
                            json={
                                "checkpoint_id": pending[0]["checkpoint_id"],
                                "decision": "approve",
                                "reviewer": "foundry-evaluation",
                                "comments": "Automated evaluation approval",
                            },
                        )
                    ).raise_for_status()
                elif details.get("status") in {"completed", "escalated"}:
                    latest_output = details.get("latest_output") or {}
                    captures.append(
                        {"query": query, "response": str(latest_output.get("message", ""))}
                    )
                    break
                elif details.get("status") == "failed":
                    raise RuntimeError(f"Workflow {thread_id} failed during evaluation capture.")
                await asyncio.sleep(1)
            else:
                raise TimeoutError(
                    f"Workflow {thread_id} did not complete during evaluation capture."
                )
    return captures


async def run_foundry_eval() -> None:
    root = Path(__file__).resolve().parents[1]
    foundry_root = root / ".foundry"
    config = _read_eval_config(root / "eval.yaml")

    dataset = config.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError("backend/eval.yaml is missing dataset mapping")
    local_uri = dataset.get("local_uri")
    if not isinstance(local_uri, str) or not local_uri.strip():
        raise ValueError("backend/eval.yaml dataset.local_uri is required")

    dataset_path = root / local_uri
    foundry_cfg = config.get("foundry")
    if not isinstance(foundry_cfg, dict):
        raise ValueError("backend/eval.yaml is missing foundry config block")

    eval_name = str(foundry_cfg.get("name", "order-resolution-foundry-report"))
    report_case_ids_raw = foundry_cfg.get("report_case_ids", [])
    if (
        not isinstance(report_case_ids_raw, list)
        or not report_case_ids_raw
        or not all(isinstance(case_id, str) and case_id for case_id in report_case_ids_raw)
    ):
        raise ValueError("backend/eval.yaml foundry.report_case_ids must be a non-empty list")
    report_case_ids = [str(case_id) for case_id in report_case_ids_raw]
    if len(set(report_case_ids)) != len(report_case_ids):
        raise ValueError("backend/eval.yaml foundry.report_case_ids must not contain duplicates")
    selected_queries = _load_report_queries(dataset_path, report_case_ids)

    evaluators_raw = foundry_cfg.get("evaluators", [])
    if not isinstance(evaluators_raw, list) or not all(
        isinstance(name, str) and name for name in evaluators_raw
    ):
        raise ValueError("backend/eval.yaml foundry.evaluators must be a list of evaluator names")
    evaluators = [str(name) for name in evaluators_raw]
    poll_interval = float(
        os.getenv("FOUNDRY_EVAL_POLL_INTERVAL", foundry_cfg.get("poll_interval", 5.0))
    )
    timeout = float(os.getenv("FOUNDRY_EVAL_TIMEOUT", foundry_cfg.get("timeout", 300.0)))
    api_url = os.getenv("FOUNDRY_EVAL_API_URL", "http://localhost:8000")

    report_path = foundry_root / "results" / "foundry-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "status": "failed",
        "provider": "foundry",
        "case_ids": report_case_ids,
        "query_count": len(selected_queries),
        "evaluators": evaluators,
        "api_url": api_url,
    }
    try:
        models_cfg = get_foundry_models_config()
        if models_cfg is None:
            raise RuntimeError(
                "Foundry model configuration is missing. Set FOUNDRY_PROJECTS_ENDPOINT and "
                "FOUNDRY_MODEL_DEPLOYMENT_NAME."
            )
        judge_model = os.getenv("FOUNDRY_EVAL_MODEL", models_cfg.model)
        credential = DefaultAzureCredential()
        project_client = AIProjectClient(
            endpoint=models_cfg.project_endpoint, credential=credential
        )
        openai_client = project_client.get_openai_client()

        testing_criteria = []
        for evaluator_name in evaluators:
            testing_criteria.append(
                {
                    "type": "azure_ai_evaluator",
                    "name": evaluator_name,
                    "evaluator_name": f"builtin.{evaluator_name}",
                    "initialization_parameters": {"deployment_name": judge_model},
                    "data_mapping": {
                        "query": "{{item.query}}",
                        "response": "{{item.response}}",
                    },
                }
            )

        eval_object = await openai_client.evals.create(
            name=eval_name,
            data_source_config={
                "type": "custom",
                "item_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "response": {"type": "string"},
                    },
                    "required": ["query", "response"],
                },
                "include_sample_schema": True,
            },
            testing_criteria=testing_criteria,
        )

        eval_run = await openai_client.evals.runs.create(
            eval_id=eval_object.id,
            name=f"{eval_name} Run",
            data_source={
                "type": "jsonl",
                "source": {
                    "type": "file_content",
                    "content": [
                        {"item": item, "sample": {}}
                        for item in await _capture_app_outputs(selected_queries, api_url)
                    ],
                },
            },
        )

        start = asyncio.get_running_loop().time()
        while str(eval_run.status) not in {"completed", "failed", "cancelled"}:
            if asyncio.get_running_loop().time() - start > timeout:
                raise TimeoutError(f"Foundry eval run timed out after {timeout} seconds")
            await asyncio.sleep(poll_interval)
            eval_run = await openai_client.evals.runs.retrieve(
                run_id=eval_run.id,
                eval_id=eval_object.id,
            )

        payload = {
            "status": str(eval_run.status),
            "provider": "foundry",
            "eval_id": eval_object.id,
            "run_id": eval_run.id,
            "case_ids": report_case_ids,
            "query_count": len(selected_queries),
            "evaluators": evaluators,
            "result_counts": _to_jsonable(getattr(eval_run, "result_counts", None)),
            "report_url": (
                f"{models_cfg.project_endpoint.rstrip('/')}/evaluation/evaluations/{eval_object.id}/runs/{eval_run.id}"
            ),
            "error": _to_jsonable(getattr(eval_run, "error", None)),
        }
    except Exception as exc:  # noqa: BLE001
        payload["status"] = (
            "timeout" if isinstance(exc, TimeoutError) else str(payload.get("status") or "failed")
        )
        payload["error"] = str(exc)
        if "eval_object" in locals():
            payload["eval_id"] = getattr(eval_object, "id", None)
        if "eval_run" in locals():
            payload["run_id"] = getattr(eval_run, "id", None)
            payload["run_status"] = str(getattr(eval_run, "status", "unknown"))
        if payload.get("eval_id") and payload.get("run_id"):
            payload["report_url"] = (
                f"{models_cfg.project_endpoint.rstrip('/')}/evaluation/evaluations/"
                f"{payload['eval_id']}/runs/{payload['run_id']}"
            )
    finally:
        if "openai_client" in locals():
            await openai_client.close()
        if "project_client" in locals():
            await project_client.close()
        if "credential" in locals():
            await credential.close()

    report_path.write_text(json.dumps(_to_jsonable(payload), indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"Foundry report saved to: {report_path}")

    enforce_pass = os.getenv("FOUNDRY_EVAL_ENFORCE_PASS", "false").lower() in {"1", "true", "yes"}
    if enforce_pass and str(payload.get("status")) != "completed":
        raise RuntimeError(f"Foundry eval run ended with status: {payload.get('status')}")


if __name__ == "__main__":
    asyncio.run(run_foundry_eval())
