from __future__ import annotations

TRIAGE_INSTRUCTIONS = (
    "Extract order issue summary in one concise sentence. If order id is missing, infer unknown."
)

POLICY_INSTRUCTIONS = "Assess policy risk in one concise sentence."

RESOLUTION_INSTRUCTIONS = "Suggest final action in one concise sentence."


def render_triage_instructions() -> str:
    return TRIAGE_INSTRUCTIONS


def render_policy_instructions() -> str:
    return POLICY_INSTRUCTIONS


def render_resolution_instructions() -> str:
    return RESOLUTION_INSTRUCTIONS
