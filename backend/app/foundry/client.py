from __future__ import annotations

import subprocess
from typing import Any

import httpx
from app.foundry.config import FoundryHostedConfig
from app.foundry.models import FoundryInvocationResponse
from app.modules.order_resolution.models import WorkflowContext
from azure.identity import DefaultAzureCredential
from opentelemetry.propagate import inject


class FoundryHostedClient:
    def __init__(self, config: FoundryHostedConfig) -> None:
        self._config = config
        self._credential: DefaultAzureCredential | None = None

    async def start_workflow(self, context: WorkflowContext) -> FoundryInvocationResponse:
        payload = {
            "operation": "start_workflow",
            "thread_id": context.thread_id,
            "workflow_run_id": context.run_id,
            "session_id": context.session_id,
            "customer_id": context.customer_id,
            "message": context.user_message,
        }
        response = await self.invoke_raw(payload)
        return FoundryInvocationResponse.model_validate(response)

    async def resume_hitl(
        self,
        *,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
        thread_id: str | None = None,
        action: str | None = None,
        order_id: str | None = None,
        amount: float | int | None = None,
    ) -> FoundryInvocationResponse:
        payload = {
            "operation": "resume_hitl",
            "checkpoint_id": checkpoint_id,
            "decision": decision,
            "reviewer": reviewer,
            "comments": comments,
        }
        if thread_id:
            payload["thread_id"] = thread_id
        if action:
            payload["action"] = action
        if order_id:
            payload["order_id"] = order_id
        if amount is not None:
            payload["amount"] = amount
        response = await self.invoke_raw(payload)
        return FoundryInvocationResponse.model_validate(response)

    async def invoke_raw(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        # Propagate W3C trace context to Foundry-hosted invocations so upstream
        # services can correlate dependency traces.
        inject(headers)
        if "services.ai.azure.com" in self._config.invocations_url:
            # Hosted Agents invoke route is currently preview-gated.
            headers["Foundry-Features"] = "HostedAgents=V1Preview"
        if self._config.api_key:
            api_key = self._config.api_key.strip()
            if api_key.lower().startswith("bearer "):
                headers["Authorization"] = api_key
            elif _looks_like_jwt(api_key):
                headers["Authorization"] = f"Bearer {api_key}"
            else:
                # Support account/project key auth for local testing without token minting.
                headers["api-key"] = api_key
        elif "services.ai.azure.com" in self._config.invocations_url:
            headers["Authorization"] = f"Bearer {self._get_foundry_bearer_token()}"
        if self._config.callback_token:
            headers["X-Foundry-Callback-Token"] = self._config.callback_token

        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                response = await client.post(
                    self._config.invocations_url,
                    json=payload,
                    headers=headers,
                )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError("Timed out invoking Foundry hosted workflow.") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ValueError("Foundry hosted checkpoint or thread was not found.") from exc
            raise RuntimeError(
                f"Foundry hosted workflow returned {exc.response.status_code}: "
                f"{exc.response.text[:512]}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Failed to invoke Foundry hosted workflow: {exc}") from exc

        response_payload = response.json()
        if not isinstance(response_payload, dict):
            raise RuntimeError("Foundry hosted workflow returned a non-object JSON payload.")
        return response_payload

    def _get_foundry_bearer_token(self) -> str:
        try:
            if self._credential is None:
                self._credential = DefaultAzureCredential(
                    exclude_interactive_browser_credential=True
                )
            token = self._credential.get_token("https://ai.azure.com/.default")
            return token.token
        except Exception:
            pass

        # Fallback for local dev: use Azure CLI token directly.
        try:
            az_token = subprocess.check_output(
                [
                    "az",
                    "account",
                    "get-access-token",
                    "--resource",
                    "https://ai.azure.com",
                    "--query",
                    "accessToken",
                    "-o",
                    "tsv",
                ],
                text=True,
                stderr=subprocess.STDOUT,
            ).strip()
            if az_token:
                return az_token
        except FileNotFoundError as az_exc:
            raise RuntimeError(
                "Unable to acquire Entra bearer token for Foundry because Azure CLI (`az`) "
                "is not available in backend runtime. Provide FOUNDRY_HOSTED_API_KEY "
                "or run backend in an environment with `az login` available."
            ) from az_exc
        except Exception as az_exc:
            detail = str(az_exc).splitlines()[0][:240]
            raise RuntimeError(
                "Unable to acquire Entra bearer token for Foundry. "
                "Run `az login` and `az account set --subscription <id-or-name>`, "
                "or provide FOUNDRY_HOSTED_API_KEY. "
                f"Azure CLI fallback error: {detail}"
            ) from az_exc

        raise RuntimeError(
            "Unable to acquire Entra bearer token for Foundry. "
            "Run `az login` and `az account set --subscription <id-or-name>`, "
            "or provide FOUNDRY_HOSTED_API_KEY."
        )


def _looks_like_jwt(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 3:
        return False
    return all(part.strip() for part in parts)
