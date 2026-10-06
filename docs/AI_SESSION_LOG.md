# AI-assisted development log

This project was built with Claude Code as a pair programmer: I directed the work and made the decisions, and Claude planned, implemented and verified. This log summarises how the sessions went: the instructions, the decisions taken and the corrections along the way. The working context Claude kept between sessions is checked in alongside it:

- [`CLAUDE.md`](../CLAUDE.md): project guidance loaded at the start of every session
- [`TASKS.md`](../TASKS.md): the execution plan, with per-task status
- [`.claude/memory/`](../.claude/memory/): persistent memory (project status plus working preferences), linked live from Claude Code's memory location
- [`.claude/plans/`](../.claude/plans/): the plans produced in plan mode (the initial exercise plan and the GitHub check-in plan)

## 1. Planning
- Started from the brief in `take-home-assignment.md`. Asked Claude for a plan first, in plan mode, then a full `CLAUDE.md` and a numbered task list where every task has Input / Files / Accept / **Verify**, plus runnable checkpoints after each exercise.
- Decisions recorded up front: OpenAI or local models, configurable per component; routing "send" is log-only; metadata enrichment uses LLM structured output; people fields (attendees, authors) come only from source parsing, never from the LLM.

## 2. Exercise 1: ingestion, enrichment, query API
- **Parsing:** docling for parsing, LangChain for orchestration, ChromaDB for vectors, SQLite for structured data.
- **Chunking:** I rejected fixed 1000-character chunking. Claude replaced it with structure-aware recursive chunking: split on headings, merge small sections, and recursively split only oversized ones by paragraph / speaker turn / sentence within a token budget.
- **Models:** I rejected fake test models. Providers are OpenAI (`gpt-4o-mini`, `text-embedding-3-small`) or local Ollama (`qwen2.5:7b`, `nomic-embed-text`), and tests run against real local models.
- **Retrieval:** semantic + BM25, merged with weighted reciprocal rank fusion, then LLM reranking.
- **Reranking:** Claude's verification caught that the first reranker, which scored all passages in one call, misaligned scores on the 7B model; it ranked an Eagle-5 passage top for a Falcon-7 question. It was switched to scoring each passage separately, with a one-sentence reason before each score.
- **Filters:** after I asked whether metadata filtering happened before retrieval, person and date filters were changed from post-filters to true pre-filters (doc ids resolved in SQLite, then pushed into Chroma, with BM25 limited to the same set).

## 3. Exercise 2: Office documents, traceability, routing, gaps
- **Office loader:** a docling-based loader for docx/pptx/xlsx, with one section per slide or sheet so citations carry a location. Authors, reviewers and roles are read from document properties or "Author: Name, Role" bylines.
- **Data finding:** Claude found the dataset's `.pptx` files were plain text, byte-identical to their `_slides.md` copies, and the `.docx` files were bare packages with literal markdown. At my request they were rebuilt into properly formatted Office files, which I verified open in Microsoft Office. The one-off conversion script was then deleted.
- **Business rules:** priority floors for line-down / safety / escalation language; action-item owners and products must appear in the source; uncited claims are dropped; the newest source wins on conflict.
- **Answers:** a streamed answer is validated after generation. Citations are re-attached or removed, uncited statements are dropped, and a confidence score is computed.
- **Low confidence:** triggers routing (who to ask, why, a draft question) and creates a knowledge-gap record.
- **Feedback:** corrections and rejections are captured with the original question and answer and surface in a review queue.
- **Instrumentation:** per-answer quality metrics with windowed alerts and drift detection versus the previous window.
- **Evals:** a golden set (written from one report) plus an LLM-generated synthetic set, measuring hit rate, MRR, faithfulness, answerability, keyword recall and citation validity.

## 4. Exercise 3: web application
- **Stack:** React + TypeScript + Vite + Tailwind.
- **Chat:** streaming chat (SSE) with conversation history and follow-up rewriting; inline citation chips with a hover source card and click-to-open document view (the cited passage is highlighted).
- **Routing and feedback:** the routing panel has an editable draft question; answers can be rated, corrected or rejected; the review queue is aimed at a team lead.
- **Extra pages I asked for:** Documents, Monitoring and Evals.
- **Guardrails:** prompt-injection blocking, off-topic refusal, PII redaction on the live token stream, and grounding.
- **UI verification:** Claude drove every page in a real browser (Playwright) and reviewed screenshots. Fixed along the way: a missing streaming caret, raw markdown in hover cards, routing ranking and casing, eval judge score scaling, and chart axis and label collisions. Charts use a palette validated for colour-blind safety in both themes.

## 5. Working agreements that shaped the sessions
- Ask before every commit and push; scan for secrets and personal data before pushing.
- In `TASKS.md`, only update statuses and add notes; never rewrite tasks. (Claude once replaced sections wholesale; the file was restored from git and only statuses were changed.)
- Don't read the dataset unless asked, and keep test fixtures minimal.
- Run checks read-only and confirm before changing anything outside the code (configuration, data, memory).
- **Added near the end (2026-10-06):** a `PostToolUse` hook in `.claude/settings.json` that runs `ruff format` and `ruff check --fix` on every backend Python file Claude edits, and returns any remaining lint errors to Claude. Also a project skill, `.claude/skills/verify/SKILL.md`, that packages the Verify steps from `TASKS.md` (lint, unit tests, integration test if Ollama is up, frontend build, plus the golden eval and smoke scripts on request). Earlier, these checks were run by hand.

## 6. Verification snapshot
- **Backend:** unit tests plus an end-to-end test against local Ollama covering ingest, citations, chat streaming and follow-ups, guardrails, routing, reject/correct, the review queue and metrics. Smoke scripts `scripts/smoke_ex1.sh` and `scripts/smoke_ex2.sh` pass against a live server.
- **Frontend:** `npm run build` passes, and a browser walkthrough of all pages had no console errors.
- **Still open:** the full real-data ingest, the golden eval on real data, and confidence-threshold calibration (see `TASKS.md`).
