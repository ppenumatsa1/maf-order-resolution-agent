#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TARGETS = ("local", "azure", "foundry")
TERMINAL_STATUSES = {"completed", "failed", "escalated"}


@dataclass(frozen=True)
class TargetConfig:
    name: str
    api_url: str
    web_url: str


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Env file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _request_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url=url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {detail}") from exc


def _wait_for_status(
    api_base: str,
    thread_id: str,
    *,
    timeout_seconds: float,
    poll_seconds: float,
    allowed_statuses: set[str],
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last_payload = _request_json("GET", f"{api_base}/api/workflows/{thread_id}")
        status = str(last_payload.get("status"))
        if status in allowed_statuses:
            return last_payload
        time.sleep(poll_seconds)
    raise TimeoutError(
        f"Timed out waiting for workflow {thread_id}; "
        f"last_status={last_payload.get('status') if last_payload else 'unknown'}"
    )


def _event_types(details: dict[str, Any]) -> list[str]:
    return [str(event.get("type")) for event in details.get("events", [])]


def _lookup_path(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _event_payloads(details: dict[str, Any], event_type: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for event in details.get("events", []):
        if str(event.get("type")) != event_type:
            continue
        payload = event.get("payload")
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _contains_value(value: Any, expected: str) -> bool:
    if isinstance(value, str):
        return expected in value
    if isinstance(value, dict):
        return any(_contains_value(v, expected) for v in value.values())
    if isinstance(value, list):
        return any(_contains_value(v, expected) for v in value)
    return False


def _evaluate_contract_case(
    api_base: str,
    case: dict[str, Any],
    *,
    timeout_seconds: float,
    poll_seconds: float,
) -> dict[str, Any]:
    run = _request_json(
        "POST",
        f"{api_base}/api/chat/run",
        {"message": case["prompt"], "customer_id": "parity-checker"},
    )
    thread_id = str(run["thread_id"])
    details = _wait_for_status(
        api_base,
        thread_id,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
        allowed_statuses=TERMINAL_STATUSES | {"waiting_approval"},
    )

    if "decision" in case:
        approvals = details.get("pending_approvals") or []
        if not approvals:
            return {
                "case_id": case["id"],
                "thread_id": thread_id,
                "passed": False,
                "failures": ["expected pending approval but none was present"],
            }
        checkpoint_id = approvals[0]["checkpoint_id"]
        _request_json(
            "POST",
            f"{api_base}/api/hitl/respond",
            {
                "checkpoint_id": checkpoint_id,
                "decision": case["decision"],
                "reviewer": "parity-runner",
                "comments": f"{case['decision']} from parity runner",
            },
        )
        details = _wait_for_status(
            api_base,
            thread_id,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
            allowed_statuses=TERMINAL_STATUSES,
        )
    elif str(details.get("status")) not in TERMINAL_STATUSES:
        details = _wait_for_status(
            api_base,
            thread_id,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
            allowed_statuses=TERMINAL_STATUSES,
        )

    failures: list[str] = []
    emitted = set(_event_types(details))
    has_hitl = "hitl.request" in emitted
    if has_hitl != bool(case.get("expect_hitl")):
        failures.append(f"HITL expected {case.get('expect_hitl')}, observed {has_hitl}")
    for event in case.get("required_events", []):
        if event not in emitted:
            failures.append(f"missing required event: {event}")
    for event in case.get("forbidden_events", []):
        if event in emitted:
            failures.append(f"forbidden event emitted: {event}")
    required_order = case.get("required_order", [])
    if required_order:
        sequence = _event_types(details)
        position = -1
        for expected_event in required_order:
            try:
                next_position = sequence.index(expected_event, position + 1)
            except ValueError:
                failures.append(f"required order event missing: {expected_event}")
                continue
            if next_position < position:
                failures.append(f"event ordering violation at: {expected_event}")
            position = next_position
    required_payload_fields = case.get("required_payload_fields", {})
    if isinstance(required_payload_fields, dict):
        for event_type, field_paths in required_payload_fields.items():
            payloads = _event_payloads(details, str(event_type))
            if not payloads:
                failures.append(f"payload check missing event: {event_type}")
                continue
            for field_path in field_paths:
                if all(_lookup_path(payload, str(field_path)) is None for payload in payloads):
                    failures.append(
                        f"missing required payload field for {event_type}: {field_path}"
                    )
    if not _contains_value(details, "ord-100"):
        failures.append("no expected order identifier found in details payload")

    return {
        "case_id": case["id"],
        "thread_id": thread_id,
        "status": details.get("status"),
        "passed": not failures,
        "failures": failures,
    }


def _run_subprocess(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _resolve_targets(selected: list[str]) -> list[str]:
    unknown = sorted(set(selected) - set(TARGETS))
    if unknown:
        raise ValueError(f"Unsupported target(s): {', '.join(unknown)}")
    return selected


def _target_config(target: str) -> TargetConfig:
    prefix = f"PARITY_{target.upper()}"
    api = (os.getenv(f"{prefix}_API_URL") or "").strip()
    web = (os.getenv(f"{prefix}_WEB_URL") or "").strip()
    if not api:
        raise ValueError(f"Missing required env var: {prefix}_API_URL")
    if not web:
        raise ValueError(f"Missing required env var: {prefix}_WEB_URL")
    return TargetConfig(name=target, api_url=api.rstrip("/"), web_url=web.rstrip("/"))


def _load_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "cases" not in payload or not isinstance(payload["cases"], list):
        raise ValueError("contract.json must include a cases array")
    return payload


def _write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"parity-report-{ts}.json"
    md_path = output_dir / f"parity-report-{ts}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Endpoint parity report",
        "",
        f"- Generated: {report['generated_at']}",
        "",
        "| Target | Manual Matrix | Event Contract | Playwright | Overall |",
        "| --- | --- | --- | --- | --- |",
    ]
    for target in report["targets"]:
        lines.append(
            f"| {target['name']} | "
            f"{'PASS' if target['manual_matrix']['returncode'] == 0 else 'FAIL'} | "
            f"{'PASS' if target['event_contract']['passed'] else 'FAIL'} | "
            f"{'PASS' if target['playwright']['returncode'] == 0 else 'FAIL'} | "
            f"{'PASS' if target['passed'] else 'FAIL'} |"
        )
    lines.append("")
    lines.append(f"Overall result: **{'PASS' if report['passed'] else 'FAIL'}**")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    default_env_file = os.getenv("PARITY_ENV_FILE", "")
    if not default_env_file:
        candidate = Path(__file__).resolve().parents[3] / "maf-ora-central" / ".env"
        if candidate.exists():
            default_env_file = str(candidate)

    parser = argparse.ArgumentParser(description="Run local/azure/foundry endpoint parity checks.")
    parser.add_argument(
        "--targets",
        nargs="+",
        default=list(TARGETS),
        help="Targets to run (local azure foundry).",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow running a subset of targets (for quick local checks).",
    )
    parser.add_argument(
        "--env-file",
        default=default_env_file,
        help="Optional dotenv file to load parity endpoint variables from.",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path(__file__).with_name("contract.json"),
        help="Path to parity contract JSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("reports"),
        help="Directory to write parity reports.",
    )
    parser.add_argument(
        "--matrix-args",
        default=os.getenv("PARITY_MANUAL_MATRIX_ARGS", ""),
        help="Extra args for run-manual-matrix.sh.",
    )
    parser.add_argument(
        "--contract-timeout",
        type=float,
        default=90.0,
        help="Timeout in seconds per event-contract case.",
    )
    parser.add_argument(
        "--contract-poll",
        type=float,
        default=1.0,
        help="Polling interval in seconds for contract checks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    if args.env_file:
        _load_dotenv(Path(args.env_file).expanduser().resolve())

    selected_targets = _resolve_targets([target.lower() for target in args.targets])
    if not args.allow_partial and set(selected_targets) != set(TARGETS):
        raise ValueError(
            "Parity pass requires all three targets: local, azure, foundry. "
            f"Received: {', '.join(selected_targets)}"
        )

    contract = _load_contract(args.contract)
    target_results: list[dict[str, Any]] = []
    parity_passed = True

    for target_name in selected_targets:
        target = _target_config(target_name)
        matrix_command = [
            str(repo_root / "scripts/manual/run-manual-matrix.sh"),
            target.api_url,
        ]
        if args.matrix_args:
            matrix_command.extend(shlex.split(args.matrix_args))
        manual_matrix = _run_subprocess(matrix_command, cwd=repo_root)

        contract_cases: list[dict[str, Any]] = []
        contract_failures: list[str] = []
        for case in contract["cases"]:
            result = _evaluate_contract_case(
                target.api_url,
                case,
                timeout_seconds=args.contract_timeout,
                poll_seconds=args.contract_poll,
            )
            contract_cases.append(result)
            if not result["passed"]:
                contract_failures.extend(result["failures"])

        event_contract = {
            "passed": not contract_failures,
            "failures": contract_failures,
            "cases": contract_cases,
        }

        playwright = _run_subprocess(
            ["npm", "run", "test:e2e"],
            cwd=repo_root / "scripts/playwright",
            env={
                **os.environ,
                "PLAYWRIGHT_BASE_URL": target.web_url,
            },
        )

        target_passed = (
            manual_matrix["returncode"] == 0
            and event_contract["passed"]
            and playwright["returncode"] == 0
        )
        parity_passed = parity_passed and target_passed
        target_results.append(
            {
                "name": target_name,
                "api_url": target.api_url,
                "web_url": target.web_url,
                "manual_matrix": manual_matrix,
                "event_contract": event_contract,
                "playwright": playwright,
                "passed": target_passed,
            }
        )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "targets": target_results,
        "passed": parity_passed,
    }
    json_report, md_report = _write_report(report, args.output_dir)
    print(f"Parity JSON report: {json_report}")
    print(f"Parity markdown report: {md_report}")
    return 0 if parity_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
