#!/usr/bin/env python3
"""Validate the static safety contract for private-runner GitHub workflows."""

from __future__ import annotations

from pathlib import Path


WORKFLOWS = Path(".github/workflows")
DEPLOYMENT_WORKFLOWS = (
    "foundry-provision.yml",
    "foundry-deploy.yml",
)
EXPECTED_TARGETS = (
    "AZD_ENVIRONMENT_NAME: foundry-private-env",
    "TARGET_RESOURCE_GROUP: rg-maf-ora-foundry-v2",
    "TARGET_FOUNDRY_PROJECT: order-resolution",
    "TARGET_POSTGRES_DATABASE: maf_workflow",
)


def require(text: str, value: str, workflow: str) -> None:
    if value not in text:
        raise AssertionError(f"{workflow} is missing required contract: {value}")


def forbid(text: str, value: str, workflow: str) -> None:
    if value in text:
        raise AssertionError(f"{workflow} contains forbidden contract: {value}")


def validate_deployment_workflow(name: str) -> None:
    text = (WORKFLOWS / name).read_text()
    require(text, "workflow_dispatch:", name)
    require(text, "confirmation:", name)
    require(text, "environment: foundry-private-env", name)
    require(text, "- self-hosted", name)
    require(text, "- foundry-private-v2", name)
    require(text, "id-token: write", name)
    require(text, "uses: azure/login@v2", name)
    require(text, "client-id: ${{ vars.AZURE_CLIENT_ID }}", name)
    require(text, "tenant-id: ${{ vars.AZURE_TENANT_ID }}", name)
    require(text, "subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}", name)
    require(text, "azd config set auth.useAzCliAuth true", name)
    require(text, "./scripts/foundry/validate_private_runner_environment.sh", name)
    require(
        text,
        "git clean -ffdx -e infra/foundry-hosted/.azure/",
        name,
    )
    forbid(text, "pull_request:", name)
    forbid(text, "push:", name)
    forbid(text, "workflow_call:", name)
    forbid(text, "secrets.", name)
    for target in EXPECTED_TARGETS:
        require(text, target, name)


def validate() -> None:
    for name in DEPLOYMENT_WORKFLOWS:
        validate_deployment_workflow(name)

    deploy = (WORKFLOWS / "foundry-deploy.yml").read_text()
    require(deploy, "make foundry-app-deploy", "foundry-deploy.yml")
    require(
        deploy,
        "Verify active Container Apps use private ACR images",
        "foundry-deploy.yml",
    )

    provision = (WORKFLOWS / "foundry-provision.yml").read_text()
    require(provision, "make foundry-provision", "foundry-provision.yml")

    validation_name = "foundry-private-validation.yml"
    validation = (WORKFLOWS / validation_name).read_text()
    require(validation, "pull_request:", validation_name)
    require(validation, "runs-on: ubuntu-latest", validation_name)
    require(validation, "python3 scripts/github/validate_private_runner_workflows.py", validation_name)
    forbid(validation, "id-token: write", validation_name)
    forbid(validation, "uses: azure/login@v2", validation_name)
    forbid(validation, "azd provision", validation_name)
    forbid(validation, "azd deploy", validation_name)


if __name__ == "__main__":
    validate()
    print("Private runner workflow static contracts passed.")
