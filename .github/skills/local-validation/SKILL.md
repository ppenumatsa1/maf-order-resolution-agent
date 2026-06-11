---
name: local-validation
description: Run existing repository local validation gates and report actionable pass, fail, or blocker status.
---

# Local Validation Skill

Use this skill before completing implementation work that changes backend, frontend, workflow, eval, infrastructure, or runnable documentation behavior.

## Guardrails

- Run only existing repository validation commands; do not add new tools or gates.
- Keep validation surgical and simplicity-first: choose the smallest existing gate set that proves the change.
- Prefer local reproducibility and clear rerun commands over broad investigation.
- Do not mask failures; report the first failing command with enough context to act.

## Required gates

Run these existing local gates when applicable:

```bash
make test
make eval-backend
make test-e2e
```

Run container parity validation when the change affects Docker, container runtime, deployment packaging, or environment parity:

```bash
make docker-test
```

## Blockers

If a gate cannot run, report the blocker and exact command to rerun after it is fixed. Common blockers include:

- Docker daemon or Compose runtime unavailable for `make docker-test`.
- Browser binaries or Playwright runtime missing for `make test-e2e`.
- Missing language/runtime dependencies required by the existing Make targets.

## Reporting

- Report each command run with pass/fail/blocker status.
- Include concise failure or blocker details and rerun commands.
- State whether validation is fully done or partially blocked.
