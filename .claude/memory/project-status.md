---
name: project-status
description: "FastChip RAG take-home status as of 2026-10-06 — what's built, committed, and still open"
metadata:
  node_type: memory
  type: project
  originSessionId: 2ca11ca8-02f9-45c3-94f0-962e1f21217c
  modified: 2026-10-06T00:00:00.000Z
---

Teradyne take-home: RAG system for fictional FastChip Semiconductor (repo `github.com/mvarma0/teradyne-takehome`, public). Exercises 1–3 built; last commit `4a0310c` on branch `feature/configurable-llm-providers`.

State:
- Backend (FastAPI/LangChain/docling/Chroma+BM25/SQLite) is flattened into one module per concern (`backend/app/*.py`, see TECH.md); React frontend done. Providers configurable (openai, google_genai, ollama); tests run on local Ollama.
- Dataset: 24 meetings + 16 real OOXML Office docs (40 files), re-dated by 104 weeks to Jan–Sep 2026 (user-approved). The Office rebuild script was deliberately deleted; don't recreate it in the repo.
- Workspace tooling added 2026-10-06: ruff `PostToolUse` hook in `.claude/settings.json` and the `/verify` skill (`.claude/skills/verify/SKILL.md`). Use `/verify` before marking tasks done or committing.
- `docs/MEASUREMENT.md` rewritten (verified-answer rate, ≥70% target by day 30).

Open (TASKS.md): 1.10 real-data ingest on the 40-file set; 2.4 legacy formats; 2.14 golden eval on real data + calibrate CONFIDENCE_THRESHOLD; backlog B1 (ingest progress), B2 (infer filters from question).
Offered, not yet accepted: Hugging Face Spaces Docker deployment (Gemini free key), docs/DESIGN.md, README screenshots, CI.

Memory lives in the repo at `.claude/memory/` (Claude Code's memory path is a symlink to it), so anything saved here is shared on the next commit — keep it free of personal details. Plan snapshots are in `.claude/plans/`; the curated session summary is `docs/AI_SESSION_LOG.md`.

**Why:** lets a fresh session resume without re-deriving context. **How to apply:** read TASKS.md first; confirm with the user before ingesting real data or pushing.

Related: [[feedback-git-confirmation]], [[feedback-tasks-md-status-only]], [[feedback-data-folder]], [[feedback-no-fake-models]]
