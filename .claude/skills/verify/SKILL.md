---
name: verify
description: Run this project's standard verification (lint, backend tests, frontend build, and optionally the golden eval and smoke scripts) and report pass/fail per step. Use before marking a TASKS.md task done, before a commit, or when asked to "verify", "check everything" or "run the checks".
---

# Verify

Run the steps in order and stop at the first failure. Report each step as pass, fail (show the relevant output) or skipped (with the reason). Never mark a step passed without running it.

## Steps

1. **Lint** (from `backend/`): `uv run ruff check . && uv run ruff format --check .`
2. **Unit tests** (from `backend/`): `uv run pytest -m "not integration" -q`
3. **Integration test** (from `backend/`): run only if Ollama is reachable (`curl -sf -m 2 localhost:11434/api/tags`). Then run `uv run pytest -m integration -q`. If Ollama isn't reachable, report the step as skipped.
4. **Frontend build** (from `frontend/`): `npm run build`.

Run these only if the user asks for a "full" verify, or if the change touched retrieval, answering, confidence or prompts:

5. **Golden eval** (from `backend/`): `uv run python -m app.evals --dataset golden`. Compare the summary with the previous run listed by `GET /api/evals` and flag any metric that dropped.
6. **Smoke scripts** (from `backend/`): run these only if a server is up (`curl -sf localhost:8000/api/health`). Then run `./scripts/smoke_ex1.sh && ./scripts/smoke_ex2.sh`. Don't start or stop the user's server.

## Rules
- Read-only: don't fix failures as part of this skill. Report them and ask before changing code.
- Never touch `data/` (see CLAUDE.md).
- Finish with a short table of steps and results. If a step was skipped, give the reason.
