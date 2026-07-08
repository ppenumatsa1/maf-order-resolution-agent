from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

STATE_PROVIDER_CONTEXT = "stateless_context"
STATE_PROVIDER_DUAL = "dual"
STATE_PROVIDER_FOUNDRY_NATIVE = "foundry_native"
SUPPORTED_STATE_PROVIDERS = {
    STATE_PROVIDER_CONTEXT,
    STATE_PROVIDER_DUAL,
    STATE_PROVIDER_FOUNDRY_NATIVE,
}


@dataclass(frozen=True)
class HostedCheckpointState:
    checkpoint_id: str
    thread_id: str
    order_id: str
    action: str
    amount: float | None = None
    status: str = "pending"
    requested_at: str | None = None
    resolved_at: str | None = None
    reviewer: str | None = None
    comments: str | None = None
    decision: str | None = None
    telemetry_trace_context: dict[str, str] | None = None

    def as_resume_context(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "thread_id": self.thread_id,
            "order_id": self.order_id,
            "action": self.action,
            "status": self.status,
            "requested_at": self.requested_at or _utc_now_iso(),
        }
        if self.amount is not None:
            payload["amount"] = self.amount
        if self.resolved_at is not None:
            payload["resolved_at"] = self.resolved_at
        if self.reviewer is not None:
            payload["reviewer"] = self.reviewer
        if self.comments is not None:
            payload["comments"] = self.comments
        if self.decision is not None:
            payload["decision"] = self.decision
        if self.telemetry_trace_context is not None:
            payload["telemetry_trace_context"] = dict(self.telemetry_trace_context)
        return payload


class HostedStateStore(Protocol):
    provider_name: str

    def save_checkpoint(self, checkpoint: HostedCheckpointState) -> None: ...

    def get_checkpoint(self, checkpoint_id: str) -> HostedCheckpointState | None: ...

    def resolve_checkpoint(
        self,
        *,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> HostedCheckpointState | None: ...

    def append_conversation_item(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...


class InMemoryHostedStateStore:
    provider_name = "in_memory"

    def __init__(self, checkpoints: dict[str, dict[str, Any]]) -> None:
        self._checkpoints = checkpoints
        self._conversation_items: dict[str, list[dict[str, Any]]] = {}

    def save_checkpoint(self, checkpoint: HostedCheckpointState) -> None:
        self._checkpoints[checkpoint.checkpoint_id] = checkpoint.as_resume_context()

    def get_checkpoint(self, checkpoint_id: str) -> HostedCheckpointState | None:
        raw = self._checkpoints.get(checkpoint_id)
        if raw is None:
            return None
        return _checkpoint_from_mapping(checkpoint_id, raw)

    def resolve_checkpoint(
        self,
        *,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> HostedCheckpointState | None:
        raw = self._checkpoints.get(checkpoint_id)
        if raw is None:
            return None
        existing = _checkpoint_from_mapping(checkpoint_id, raw)
        if existing is None:
            return None
        if existing.status != "pending":
            return existing
        resolved = HostedCheckpointState(
            checkpoint_id=checkpoint_id,
            thread_id=existing.thread_id,
            order_id=existing.order_id,
            action=existing.action,
            amount=existing.amount,
            status="approved" if decision == "approve" else "rejected",
            requested_at=existing.requested_at,
            resolved_at=_utc_now_iso(),
            reviewer=reviewer,
            comments=comments,
            decision=decision,
            telemetry_trace_context=existing.telemetry_trace_context,
        )
        self._checkpoints[checkpoint_id] = resolved.as_resume_context()
        return resolved

    def append_conversation_item(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._conversation_items.setdefault(thread_id, []).append(
            {"role": role, "content": content, "metadata": metadata or {}}
        )


class ContextOnlyHostedStateStore:
    provider_name = STATE_PROVIDER_CONTEXT

    def __init__(self, process_store: InMemoryHostedStateStore) -> None:
        self._process_store = process_store

    def save_checkpoint(self, checkpoint: HostedCheckpointState) -> None:
        self._process_store.save_checkpoint(checkpoint)

    def get_checkpoint(self, checkpoint_id: str) -> HostedCheckpointState | None:
        return self._process_store.get_checkpoint(checkpoint_id)

    def resolve_checkpoint(
        self,
        *,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> HostedCheckpointState | None:
        return self._process_store.resolve_checkpoint(
            checkpoint_id=checkpoint_id,
            decision=decision,
            reviewer=reviewer,
            comments=comments,
        )

    def append_conversation_item(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._process_store.append_conversation_item(
            thread_id=thread_id,
            role=role,
            content=content,
            metadata=metadata,
        )


class FoundryNativeHostedStateStore:
    provider_name = STATE_PROVIDER_FOUNDRY_NATIVE

    def __init__(self) -> None:
        project_endpoint = _env("FOUNDRY_PROJECT_ENDPOINT") or _env("AZURE_AI_PROJECT_ENDPOINT")
        if not project_endpoint:
            raise RuntimeError(
                "FOUNDRY_HOSTED_STATE_PROVIDER=foundry_native requires "
                "FOUNDRY_PROJECT_ENDPOINT or AZURE_AI_PROJECT_ENDPOINT."
            )
        raise RuntimeError(
            "FOUNDRY_HOSTED_STATE_PROVIDER=foundry_native is not enabled yet: "
            "a durable Foundry checkpoint/state API with HITL approval audit parity "
            "must be proven before switching hosted checkpoints from explicit resume context."
        )

    def save_checkpoint(self, checkpoint: HostedCheckpointState) -> None:
        raise NotImplementedError

    def get_checkpoint(self, checkpoint_id: str) -> HostedCheckpointState | None:
        raise NotImplementedError

    def resolve_checkpoint(
        self,
        *,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> HostedCheckpointState | None:
        raise NotImplementedError

    def append_conversation_item(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        raise NotImplementedError


class DualHostedStateStore:
    provider_name = STATE_PROVIDER_DUAL

    def __init__(
        self,
        *,
        primary: HostedStateStore,
        shadow: HostedStateStore,
    ) -> None:
        self._primary = primary
        self._shadow = shadow

    def save_checkpoint(self, checkpoint: HostedCheckpointState) -> None:
        self._primary.save_checkpoint(checkpoint)
        self._shadow.save_checkpoint(checkpoint)

    def get_checkpoint(self, checkpoint_id: str) -> HostedCheckpointState | None:
        return self._primary.get_checkpoint(checkpoint_id)

    def resolve_checkpoint(
        self,
        *,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> HostedCheckpointState | None:
        resolved = self._primary.resolve_checkpoint(
            checkpoint_id=checkpoint_id,
            decision=decision,
            reviewer=reviewer,
            comments=comments,
        )
        self._shadow.resolve_checkpoint(
            checkpoint_id=checkpoint_id,
            decision=decision,
            reviewer=reviewer,
            comments=comments,
        )
        return resolved

    def append_conversation_item(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._primary.append_conversation_item(
            thread_id=thread_id,
            role=role,
            content=content,
            metadata=metadata,
        )
        self._shadow.append_conversation_item(
            thread_id=thread_id,
            role=role,
            content=content,
            metadata=metadata,
        )


def build_hosted_state_store(
    checkpoints: dict[str, dict[str, Any]],
) -> HostedStateStore:
    provider = (_env("FOUNDRY_HOSTED_STATE_PROVIDER") or STATE_PROVIDER_CONTEXT).lower()
    if provider not in SUPPORTED_STATE_PROVIDERS:
        raise RuntimeError(
            "FOUNDRY_HOSTED_STATE_PROVIDER must be one of: "
            + ", ".join(sorted(SUPPORTED_STATE_PROVIDERS))
        )

    process_store = InMemoryHostedStateStore(checkpoints)
    if provider == STATE_PROVIDER_CONTEXT:
        return ContextOnlyHostedStateStore(process_store)
    if provider == STATE_PROVIDER_FOUNDRY_NATIVE:
        return FoundryNativeHostedStateStore()
    return DualHostedStateStore(
        primary=ContextOnlyHostedStateStore(process_store), shadow=FoundryNativeHostedStateStore()
    )


def _checkpoint_from_mapping(
    checkpoint_id: str, raw: dict[str, Any]
) -> HostedCheckpointState | None:
    thread_id = raw.get("thread_id")
    order_id = raw.get("order_id")
    action = raw.get("action")
    if not all(isinstance(value, str) and value for value in (thread_id, order_id, action)):
        return None
    amount = raw.get("amount")
    trace_context = raw.get("telemetry_trace_context")
    return HostedCheckpointState(
        checkpoint_id=checkpoint_id,
        thread_id=thread_id,
        order_id=order_id,
        action=action,
        amount=float(amount) if isinstance(amount, int | float) else None,
        status=str(raw.get("status") or "pending"),
        requested_at=_optional_str(raw.get("requested_at")),
        resolved_at=_optional_str(raw.get("resolved_at")),
        reviewer=_optional_str(raw.get("reviewer")),
        comments=_optional_str(raw.get("comments")),
        decision=_optional_str(raw.get("decision")),
        telemetry_trace_context=trace_context if isinstance(trace_context, dict) else None,
    )


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
