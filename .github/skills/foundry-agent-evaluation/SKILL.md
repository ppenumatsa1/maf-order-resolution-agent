---
name: foundry-agent-evaluation
description: Run deterministic and Foundry report-only evaluations for the hosted order-resolution agent, publish artifacts, and enforce evaluation guardrails.
---

# Foundry Agent Evaluation Skill

Use this skill for any workflow/runtime/HITL change that needs agent-quality evidence.

## Scope

- Canonical dataset: `backend/.foundry/datasets/order-resolution-hosted-cases.jsonl`
- Deterministic contract runner: `backend/evals/eval_runner.py`
- Foundry report runner: `backend/evals/foundry_eval_runner.py`
- Declarative config: `backend/eval.yaml`

## Execution model

1. Run deterministic contract checks (blocking):

```bash
make eval-backend
```

2. Run Foundry evaluation (report-only by default):

```bash
make eval-foundry
```

3. Optional combined command:

```bash
make eval-all
```

## Guardrails

- Keep one source-controlled golden dataset under `backend/.foundry/datasets/`.
- Do not treat generated responses/reports as business truth.
- Keep deterministic checks blocking and exact for HITL state/event/status contracts.
- Keep Foundry evaluator results report-only unless `FOUNDRY_EVAL_ENFORCE_PASS=true` is explicitly set.
- Run tool evaluators only when dataset/tool traces explicitly support them.

## Required evidence

- `backend/.foundry/results/report.json`
- `backend/.foundry/results/contract_capture.json`
- `backend/.foundry/results/foundry-report.json`
