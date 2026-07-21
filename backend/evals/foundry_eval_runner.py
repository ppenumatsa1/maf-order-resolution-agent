from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import yaml
from agent_framework.foundry import FoundryEvals
from app.maf.clients import get_foundry_models_config
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential


def _read_eval_config(path: Path) -> dict[str, object]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("backend/eval.yaml must be a mapping")
    return config


def _load_queries(dataset_path: Path) -> tuple[list[str], bool, bool]:
    queries: list[str] = []
    includes_groundedness = False
    includes_tool_evals = False
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        query = row.get("input")
        if isinstance(query, str) and query.strip():
            queries.append(query.strip())
        if bool(row.get("requires_grounded_policy_answer", False)):
            includes_groundedness = True
        if bool(row.get("include_tool_evaluators", False)):
            includes_tool_evals = True
    return queries, includes_groundedness, includes_tool_evals


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
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
    queries, includes_groundedness, includes_tool_evals = _load_queries(dataset_path)
    if not queries:
        raise ValueError(f"No queries found in dataset: {dataset_path}")

    foundry_cfg = config.get("foundry")
    if not isinstance(foundry_cfg, dict):
        raise ValueError("backend/eval.yaml is missing foundry config block")

    eval_name = str(foundry_cfg.get("name", "order-resolution-foundry-report"))
    max_queries = int(foundry_cfg.get("max_queries", len(queries)))
    base_evaluators_raw = foundry_cfg.get("evaluators", [])
    if not isinstance(base_evaluators_raw, list) or not all(
        isinstance(name, str) and name for name in base_evaluators_raw
    ):
        raise ValueError("backend/eval.yaml foundry.evaluators must be a list of evaluator names")
    base_evaluators = [str(name) for name in base_evaluators_raw]

    optional_groundedness = str(
        foundry_cfg.get("optional_groundedness_evaluator", FoundryEvals.GROUNDEDNESS)
    )
    optional_tool_evaluators = foundry_cfg.get("optional_tool_evaluators", [])
    if not isinstance(optional_tool_evaluators, list) or not all(
        isinstance(name, str) and name for name in optional_tool_evaluators
    ):
        raise ValueError("backend/eval.yaml foundry.optional_tool_evaluators must be a list")

    evaluators = list(base_evaluators)
    if includes_groundedness:
        evaluators.append(optional_groundedness)
    if includes_tool_evals:
        evaluators.extend(str(name) for name in optional_tool_evaluators)
    evaluators = _dedupe(evaluators)

    selected_queries = queries[: max_queries if max_queries > 0 else len(queries)]
    if not selected_queries:
        raise ValueError("No queries selected for Foundry evaluation")

    models_cfg = get_foundry_models_config()
    if models_cfg is None:
        raise RuntimeError(
            "Foundry model configuration is missing. Set FOUNDRY_PROJECTS_ENDPOINT and "
            "FOUNDRY_MODEL_DEPLOYMENT_NAME."
        )
    judge_model = os.getenv("FOUNDRY_EVAL_MODEL", models_cfg.model)
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
        "query_count": len(selected_queries),
        "evaluators": evaluators,
        "api_url": api_url,
    }
    try:
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
        report_path.write_text(json.dumps(_to_jsonable(payload), indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        print(f"Foundry report saved to: {report_path}")
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
