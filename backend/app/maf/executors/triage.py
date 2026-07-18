from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.telemetry import observe_maf_workflow_event
from app.maf.agents import create_order_resolution_agents
from app.maf.clients import create_foundry_chat_client, get_foundry_models_config
from app.maf.middleware import MafUsageTracker
from app.modules.order_resolution.hitl import classify_issue
from app.modules.order_resolution.models import WorkflowContext


@dataclass(frozen=True)
class TriageResult:
    summary: str
    used_foundry_models: bool


class TriageExecutor:
    def __init__(self, sequential_builder_cls: type[Any], usage_tracker: MafUsageTracker) -> None:
        self._SequentialBuilder = sequential_builder_cls
        self._usage_tracker = usage_tracker

    async def run(
        self,
        *,
        message: str,
        context_summary: str,
        workflow_context: WorkflowContext,
    ) -> TriageResult:
        config = get_foundry_models_config()
        if config is None:
            return TriageResult(
                summary=f"triage_summary: {self.simple_summary(message)}",
                used_foundry_models=False,
            )

        client, credential, _ = create_foundry_chat_client(config)
        try:
            triage_agent, policy_agent, resolution_agent = create_order_resolution_agents(
                client,
                workflow_context=workflow_context,
            )
            workflow = self._SequentialBuilder(
                participants=[triage_agent, policy_agent, resolution_agent],
                intermediate_output_from=[triage_agent, policy_agent],
            ).build()
            input_text = f"context:\n{context_summary}\n\nrequest:\n{message}"
            final_output: Any | None = None
            stream = workflow.run(message=input_text, stream=True)
            async for event in stream:
                observe_maf_workflow_event(event, workflow_name="order_resolution")
                self._usage_tracker.observe_stream_event(
                    event,
                    workflow_name="order_resolution",
                    context=workflow_context,
                )
                if getattr(event, "type", None) == "output":
                    final_output = getattr(event, "data", None)

            if final_output is None:
                result = await stream.get_final_response()
                outputs = result.get_outputs()
                final_output = outputs[-1] if outputs else ""
            return TriageResult(summary=str(final_output), used_foundry_models=True)
        finally:
            close = getattr(credential, "close", None)
            if close is not None:
                await close()

    @staticmethod
    def simple_summary(message: str) -> str:
        msg = message.lower()
        issue_type = classify_issue(msg)
        order_id = "ord-1009" if "1009" in msg else "ord-1001"
        return f"order_id={order_id}; issue_type={issue_type}"
