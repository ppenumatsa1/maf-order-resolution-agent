from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.core.config import get_config
from app.infrastructure.events import EventBus
from app.infrastructure.mcp import MCPKnowledgeTool
from app.infrastructure.persistence import CheckpointStore
from app.infrastructure.persistence.session_memory import create_memory_store
from app.infrastructure.rag import PolicyKnowledgeIngestion, create_rag_provider
from app.maf.factory import create_workflow
from app.modules.order_resolution.models import WorkflowContext


async def run_eval() -> None:
    root = Path(__file__).resolve().parents[1]
    foundry_root = root / ".foundry"
    cases_path = foundry_root / "datasets" / "order-resolution-hosted-cases.jsonl"
    config = get_config()

    event_bus = EventBus()
    memory_store = create_memory_store(config.memory_provider, foundry_root / "memory")
    checkpoint_store = CheckpointStore(foundry_root / "checkpoints")
    rag_provider = create_rag_provider(config.rag_provider)
    if config.rag_provider == "pgvector":
        await PolicyKnowledgeIngestion(rag_provider).ingest_defaults_safe()
    workflow = create_workflow(
        config=config,
        event_bus=event_bus,
        memory_store=memory_store,
        checkpoint_store=checkpoint_store,
        mcp_tool=MCPKnowledgeTool(endpoint=None),
        rag_provider=rag_provider,
    )

    total = 0
    passed = 0
    results = []

    for line in cases_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        total += 1

        thread_id = str(uuid4())
        context = WorkflowContext(
            run_id=str(uuid4()),
            thread_id=thread_id,
            session_id=thread_id,
            customer_id="eval-user",
            user_message=case["input"],
        )
        await workflow.start(context)

        history = json.loads(event_bus.history_as_json(thread_id))
        has_hitl = any(event["type"] == "hitl.request" for event in history)
        if has_hitl:
            checkpoint = next(
                (event for event in history if event["type"] == "checkpoint.created"),
                None,
            )
            if checkpoint is None:
                results.append(
                    {
                        "id": case["id"],
                        "expect_hitl": case["expect_hitl"],
                        "actual_hitl": has_hitl,
                        "has_output": False,
                        "passed": False,
                        "error": "checkpoint.created missing",
                    }
                )
                continue
            await workflow.handle_hitl_response(
                checkpoint_id=checkpoint["payload"]["checkpoint_id"],
                decision="approve",
                reviewer="eval-bot",
                comments="auto-approve for eval",
            )
            history = json.loads(event_bus.history_as_json(thread_id))

        has_output = any(event["type"] == "workflow.output" for event in history)
        verdict = has_output and has_hitl == case["expect_hitl"]
        if verdict:
            passed += 1

        results.append(
            {
                "id": case["id"],
                "expect_hitl": case["expect_hitl"],
                "actual_hitl": has_hitl,
                "has_output": has_output,
                "passed": verdict,
            }
        )

    report = {
        "total": total,
        "passed": passed,
        "pass_rate": 0 if total == 0 else round((passed / total) * 100, 2),
        "results": results,
    }
    report_path = foundry_root / "results" / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(run_eval())
