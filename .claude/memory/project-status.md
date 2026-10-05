---
name: project-status
description: "FastChip RAG take-home status as of 2026-10-06 — what's built, pushed, and still open"
metadata:
  node_type: memory
  type: project
  originSessionId: 2ca11ca8-02f9-45c3-94f0-962e1f21217c
  modified: 2026-10-05T16:18:15.030Z
---

Teradyne take-home: RAG system for fictional FastChip Semiconductor (repo `github.com/mvarma0/teradyne-takehome`, public). Exercises 1–3 built and pushed; last commit `8b509ba` "exercise 2 and 3 working code" (2026-10-06).

State:
- Backend (FastAPI/LangChain/docling/Chroma+BM25/SQLite) + React frontend done; verified only on test fixtures + generated mock Office files with local Ollama (qwen2.5:7b, nomic-embed-text). User's backend/.env uses Ollama.
- The dataset's .docx/.pptx were rebuilt into real, properly formatted OOXML at the user's request (user verified they open in Office); `_slides.md` duplicates removed; the rebuild script was deliberately deleted — don't recreate it in the repo.
- Real-data index currently has only the 20 meetings; the 15 Office docs are not ingested yet.

Open (TASKS.md): 1.10 / 2.4 real-data ingest, 2.14 golden eval on real data + calibrate CONFIDENCE_THRESHOLD; backlog B1 (ingest progress API/UI), B2 (infer filters from question).
Known stale docs: CLAUDE.md and TASKS.md status notes still say the .pptx files are plain text.
Suggested next (offered, not yet accepted): docs/DESIGN.md (decisions/tradeoffs), README screenshots, GitHub Actions CI, real eval numbers in README.

Memory lives in the repo at `.claude/memory/` (Claude Code's memory path is a symlink to it), so anything saved here is shared on the next commit — keep it free of personal details. Plan snapshots are in `.claude/plans/`; the curated session summary is `docs/AI_SESSION_LOG.md`.

**Why:** lets a fresh session resume without re-deriving context. **How to apply:** read TASKS.md first; confirm with the user before ingesting real data or pushing.

Related: [[feedback-git-confirmation]], [[feedback-tasks-md-status-only]], [[feedback-data-folder]], [[feedback-no-fake-models]]
