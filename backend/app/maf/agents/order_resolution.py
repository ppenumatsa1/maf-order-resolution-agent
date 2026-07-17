from __future__ import annotations

from typing import Any

from app.maf.middleware import create_chat_usage_middleware
from app.maf.prompts import (
    render_policy_instructions,
    render_resolution_instructions,
    render_triage_instructions,
)
from app.modules.order_resolution.models import WorkflowContext


def create_order_resolution_agents(
    client: Any,
    *,
    workflow_context: WorkflowContext,
) -> tuple[Any, Any, Any]:
    triage_agent = client.as_agent(
        name="TriageAgent",
        instructions=render_triage_instructions(),
        default_options={"store": False},
        middleware=[
            create_chat_usage_middleware(
                workflow_name="order_resolution",
                context=workflow_context,
            )
        ],
    )
    policy_agent = client.as_agent(
        name="PolicyAgent",
        instructions=render_policy_instructions(),
        default_options={"store": False},
        middleware=[
            create_chat_usage_middleware(
                workflow_name="order_resolution",
                context=workflow_context,
            )
        ],
    )
    resolution_agent = client.as_agent(
        name="ResolutionAgent",
        instructions=render_resolution_instructions(),
        default_options={"store": False},
        middleware=[
            create_chat_usage_middleware(
                workflow_name="order_resolution",
                context=workflow_context,
            )
        ],
    )
    return triage_agent, policy_agent, resolution_agent

