# TASKS

Status legend: `[x]` done (verified) · `[~]` in progress · `[ ]` to do.

> Note (2026-10-06): the backend was later flattened into one module per concern (see `TECH.md` §1). File paths in tasks written before F9 refer to the original layout. Old → current: `app/llm/*` → `llm.py`; `app/db/*` → `db.py` + `schema.sql`; `app/models/*` → `schemas.py`; `app/ingestion/loaders/*`, `docling_md.py` → `loaders.py`; `app/ingestion/{pipeline,chunking,enrich}.py` → `ingest.py`; `app/retrieval/*` → `search.py`; `app/answer/{chat,citations,confidence}.py` → `answer.py`; `app/answer/guardrails.py` → `guardrails.py`; `app/answer/business_rules.py` → `rules.py`; `app/routing/*`, `app/feedback/*` → `feedback.py`; `app/observability/*` → `metrics.py`; `app/evals/*` → `evals.py`; `app/api/*` → `api.py`.
>
> Note (2026-10-06): the dataset was re-dated by 104 weeks (2024 → 2026, weekdays preserved) and now holds 24 meetings + 16 Office documents (40 files). Older status notes and examples that mention 2024 dates, "20 meetings + 15 documents" or 35 files predate this change.

Execute in order. Each task lists **Input** (what must exist), **Files** (what it creates or modifies), **Accept** (acceptance criteria) and **Verify** (the command or check). Mark `[x]` only after Verify passes. Commands assume `backend/` or `frontend/` as cwd unless noted.

---

## Phase 0: Setup

- [x] **0.1 Project docs + git**
  - Input: empty repo
  - Files: `CLAUDE.md`, `TASKS.md`, `.gitignore`
  - Accept: CLAUDE.md holds full context; git repo initialized
  - Verify: `git status` shows the repo; `cat CLAUDE.md | head`

- [x] **0.2 Backend scaffold**
  - Input: 0.1
  - Files: `backend/pyproject.toml`, `backend/.python-version`, `backend/.env.example`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/tests/test_health.py`, package `__init__.py` stubs
  - Accept: uv project on Python 3.12 with all deps; `/api/health` returns ok
  - Verify: `uv run pytest` passes; `uv run uvicorn app.main:app` then `curl -s localhost:8000/api/health` → `{"status":"ok"}`; `uv run ruff check .`

- [x] **0.3 Frontend scaffold**
  - Input: 0.2
  - Files: `frontend/` (Vite React-TS), `vite.config.ts` (Tailwind plugin + `/api` proxy), `src/App.tsx`, `src/index.css`
  - Accept: Tailwind works; page shows backend health status
  - Verify: `npm run build` passes; with the backend running, `npm run dev` → http://localhost:5173 shows "backend: ok"

---

## Exercise 1: Meetings → docling → recursive chunks → Chroma + hybrid retrieval API

Design: docling normalizes markdown; title/date/attendees(+roles) are parsed deterministically; LLM enrichment via structured output; **structure-aware recursive chunking** (headings → merge small sections → recursive split of oversized ones by paragraph/turn → line → sentence, token budget is an upper bound); **hybrid retrieval** = semantic (Chroma) + BM25 → weighted RRF → **pointwise LLM rerank**. Providers are configurable: `openai` (gpt-4o-mini, text-embedding-3-small) or `ollama` (qwen2.5:7b, nomic-embed-text). No fake models; tests use local Ollama.

- [x] **1.1 Config + model factory**
  - Files: `app/config.py`, `app/llm/factory.py`
  - Accept: every tunable in Settings; `get_llm()` / `get_embeddings()` / `structured_llm()` for openai|ollama; nomic task prefixes; Chroma collection suffixed by embedding model; missing OpenAI key → `ConfigError` → HTTP 503
  - Verify: `uv run pytest`; with `OPENAI_API_KEY=` and provider openai, `POST /api/query` → 503 with a clear message

- [x] **1.2 SQLite layer**
  - Files: `app/db/schema.sql` (documents, action_items, enrichment_cache), `app/db/sqlite.py`, `app/db/repository.py`
  - Accept: idempotent `init_db()` on startup; documents store attendees, roles, meeting type, location and enrichment
  - Verify: `uv run pytest` (integration test reads documents back through the API)

- [x] **1.3 Meeting loader + docling**
  - Files: `app/models/source.py`, `app/ingestion/loaders/meeting.py`, `app/ingestion/docling_md.py`
  - Accept: handles frontmatter, label lines (`Meeting:`, `Date: … Time: …`, `Attendees: Name (Role), …`), `## Attendees` lists, speaker fallback; plain section labels promoted to `##`; speaker turns kept as paragraphs through docling
  - Verify: `uv run pytest tests/test_meeting_loader.py`; `uv run python -m app.ingestion --dry-run`

- [x] **1.4 Enrichment chain**
  - Files: `app/models/enrichment.py`, `app/ingestion/enrich.py`
  - Accept: topic_domain, priority, products, summary, key_topics, decisions, action_items; cached by (content hash, model, prompt version); people never from the LLM; products normalized generically
  - Verify: integration test asserts topic, products and action items

- [x] **1.5 Structure-aware recursive chunking**
  - Files: `app/ingestion/chunking.py`
  - Accept: chunks never cross headings; small sections merged (`CHUNK_MIN_TOKENS`); only sections over `CHUNK_MAX_TOKENS` split recursively; each chunk has a context header + section path + scalar metadata
  - Verify: `uv run pytest tests/test_chunking.py`

- [x] **1.6 Ingestion pipeline + CLI**
  - Files: `app/ingestion/pipeline.py`, `app/ingestion/__main__.py`, `app/retrieval/vectorstore.py`
  - Accept: load → enrich → chunk → Chroma → SQLite; skips unchanged files; prunes deleted files; per-file failures reported; concurrent runs → 409
  - Verify: integration test (ingest 3, re-run skips 3, delete 1 → removed 1)

- [x] **1.7 Hybrid retrieval + rerank**
  - Files: `app/retrieval/bm25.py`, `app/retrieval/hybrid.py`, `app/retrieval/rerank.py`, `app/retrieval/types.py`
  - Accept: semantic + BM25 candidates, weighted RRF, pointwise LLM rerank (`RERANKER=llm|none`); filters on topic/priority/source_type (Chroma `where`) and person/date range; per-result scores exposed
  - Verify: `uv run pytest tests/test_retrieval_units.py`; integration test checks exact-term BM25 hits and the person filter
  - Status: Done; later improved: person/date filters are now true pre-filters (resolved to doc ids in SQLite → `doc_id $in` in Chroma, BM25 limited to the same set).

- [x] **1.8 API**
  - Files: `app/api/routes.py`, `app/answer/generate.py`, `app/answer/service.py`, `app/models/api.py`, `app/main.py`
  - Accept: `POST /api/ingest`, `POST /api/query` (answer with [n] citations + results + derived document metadata + retrieval stats), `GET /api/documents[/{id}]`, `GET /api/stats`, `GET /api/health`
  - Verify: `./scripts/smoke_ex1.sh` against a running server

- [x] **1.9 Ex1 smoke + tests** ✅ CHECKPOINT (verified on fixtures with Ollama)
  - Files: `scripts/smoke_ex1.sh`, `tests/conftest.py`, `tests/test_*.py`, `tests/fixtures/meetings/`
  - Verify: `uv run pytest` (17 unit + 1 Ollama integration) and the smoke script, all green

- [ ] **1.10 Real-data run** (when `data/meetings/` is complete)
  - Verify: `POST /api/ingest` → `files_found` = 20, `failed` = []; check `warnings` for files without attendee lists; spot-check `GET /api/documents` topics/priorities; run `./scripts/smoke_ex1.sh`
  - Status: To do: waiting for the full real-data run (`data/` now has 20 meetings + 15 documents).
  - Status (T3 run, Gemini `gemini-3.1-flash-lite` + `gemini-embedding-001`): ingest of all 35 files done (0 failed, 173 chunks); `smoke_ex1.sh` updated for the current payload and passes on real data. **Pending:** re-ingest the 5 spreadsheets after their author properties were added, then mark done.
  - Status (2026-10-06): the dataset now has 24 meetings + 16 documents (40 files) after the quality pass; the full real-data ingest still has to be re-run against it.

---

## Exercise 2: Office docs, traceability, routing, gaps, instrumentation

- [x] **2.1 DOCX loader**
  - Input: 1.9, `data/documents/docx/`
  - Files: `app/ingestion/loaders/docx.py`, `tests/test_docx_loader.py` (fixture generated in the test)
  - Accept: paragraphs + tables as text; author from core_properties → body "Author:/Owner:" → "unknown"; date from core props
  - Verify: pytest; `uv run python -m app.ingestion --dry-run --only documents` lists 5 docx with authors
  - Status: Done: implemented as one docling-based Office loader (`app/ingestion/loaders/office.py`) covering docx/pptx/xlsx. Author/title/date/reviewers come from core properties or body bylines. Verified by `tests/test_office_and_rules.py`.

- [x] **2.2 PPTX loader**
  - Files: `app/ingestion/loaders/pptx.py`, `tests/test_pptx_loader.py`
  - Accept: one section per slide (title, text, notes) with location `slide N`; author
  - Verify: pytest; dry-run lists 5 pptx
  - Status: Done: in `office.py`, one `## Slide N` section per slide plus speaker notes. The dataset's .pptx files are plain text, so they go through the text fallback and are flagged in the report.
  - Status (2026-10-06): the dataset's .pptx files were later rebuilt as real OOXML decks, so they now go through the docling path; the text fallback remains for non-OOXML files.

- [x] **2.3 XLSX loader**
  - Files: `app/ingestion/loaders/xlsx.py`, `tests/test_xlsx_loader.py`
  - Accept: per sheet, rows rendered as `header: value` lines with location `Sheet!rows a-b`; creator as author
  - Verify: pytest; dry-run lists 5 xlsx
  - Status: Done: in `office.py`, one `## Sheet: name` section per sheet (docling markdown tables); tables split by rows with the header repeated (`chunking.py`).

- [~] **2.4 Legacy formats + unified pipeline**
  - Status (T3 run): 35 docs ingested on real data (20 meeting, 5 docx, 5 pptx, 5 xlsx). The 5 spreadsheets had no author/date properties; added author, title and date (user-approved data change, sheet contents unchanged; openpyxl + docling read them). **Pending:** re-ingest them; a LibreOffice check could not run here (Calc not installed in the sandbox).
  - Files: `app/ingestion/loaders/legacy.py`, `app/ingestion/loaders/__init__.py` (extension registry), `app/ingestion/pipeline.py`, `app/ingestion/chunking.py` (keep location metadata)
  - Accept: `.doc/.ppt/.xls` converted with `soffice --headless --convert-to` if available, else skipped with a warning; all types share one SourceDoc/enrichment path
  - Verify: `uv run python -m app.ingestion` → 35 docs; `curl -s 'localhost:8000/api/documents?source_type=xlsx' | jq length` → 5
  - Status: In progress: legacy shim and unified pipeline done, verified on fixtures plus mock Office files (7 docs). Still open: the 35-document check on the full real dataset.

- [x] **2.5 Business rules**
  - Files: `app/answer/business_rules.py`, `tests/test_business_rules.py`, hook into `enrich.py`
  - Accept: (a) people only from source; (b) claims without valid citations dropped; (c) priority escalated to critical for customer escalation / AEC-Q100 or safety / line-down; (d) one taxonomy across types; (e) newer source preferred on conflict, conflict surfaced
  - Verify: `uv run pytest tests/test_business_rules.py`
  - Status: Done: R1-R6 in `app/answer/business_rules.py` / `citations.py`; tests in `tests/test_office_and_rules.py`, plus the integration test asserting the escalation meeting becomes critical.

- [x] **2.6 Cited answer chain**
  - Files: `app/answer/generate.py`, `app/answer/citations.py`, `tests/test_answer.py`, `app/api/routes_query.py`
  - Accept: the LLM returns `claims[{text, citations[n]}]` + an answerability score; the validator drops claims citing unknown chunks; every citation carries source_file, source_type, location, authors/attendees, date, snippet, score
  - Verify: pytest; the curl query shows every claim with ≥1 citation that has source_file + a person
  - Status: Done: streamed answer + post-hoc claim extraction/validation (`app/answer/chat.py`, `citations.py`). Uncited claims are dropped; citations carry file, people, section, date, snippet and scores.

- [x] **2.7 Confidence scoring**
  - Files: `app/answer/confidence.py`, `tests/test_confidence.py`
  - Accept: weighted score from top/mean retrieval score, citation coverage and LLM answerability; `confident = score >= CONFIDENCE_THRESHOLD`
  - Verify: pytest; `curl ... -d '{"query":"What is on the cafeteria menu?"}'` → `confident:false`
  - Status: Done: `app/answer/confidence.py` (retrieval + rerank + citation coverage, with caps). Off-topic questions are now handled by guardrails before retrieval.

- [x] **2.8 Query logging**
  - Files: `app/db/schema.sql` (+queries), `app/feedback/queries.py`, `app/api/routes_query.py` (`GET /api/query/{id}`)
  - Accept: every query is persisted; the response includes `query_id`
  - Verify: POST a query, then `curl localhost:8000/api/query/<id>` returns the same answer
  - Status: Done: stored as assistant rows in the `messages` table (message id = query id); `GET /api/query/{id}`.

- [x] **2.9 Routing engine**
  - Files: `app/routing/people.py`, `app/routing/router.py`, `app/db/schema.sql` (+routing_suggestions), `tests/test_router.py`
  - Accept: candidates from authors, attendees and action-item owners of retrieved docs, scored by retrieval relevance and enriched with role/dept; `reason` names the matched files and snippets; LLM-drafted question addressed to that person; persisted
  - Verify: pytest; a query like "What is the Falcon-7 thermal margin at 150°C junction?" returns routing to the relevant design/test people with file-based reasons
  - Status: Done: `app/routing/router.py` (authors, reviewers, attendees, action-item owners; LLM draft with template fallback). Roles come from the parsed data rather than a static people.py.

- [x] **2.10 Low-confidence routing + reject**
  - Files: `app/db/schema.sql` (+gaps), `app/feedback/gaps.py`, `app/api/routes_query.py` (`POST /api/query/{id}/reject`)
  - Accept: a low-confidence query → routing in the response + a `low_confidence` gap; reject → a `rejected` gap + routing returned; query status updated
  - Verify: `curl -XPOST localhost:8000/api/query/<id>/reject -d '{"reason":"wrong lot","submitted_by":"me"}' -H 'content-type: application/json'`, then `curl localhost:8000/api/gaps`
  - Status: Done: low confidence → routing + gap; `POST /api/query/{id}/reject` → gap + routing. Verified by the integration test.

- [x] **2.11 Corrections + gaps API**
  - Files: `app/api/routes_gaps.py`, `app/api/routes_query.py` (`/correct`), `tests/test_gaps.py`
  - Accept: a correction stored with the original query, answer and citations; `GET /api/gaps?type=&status=`, `GET /api/gaps/{id}`
  - Verify: pytest; curl correct → it appears in `/api/gaps?type=correction`
  - Status: Done: `/correct`, `/api/gaps`, `/api/gaps/{id}` (`app/feedback/actions.py`, `app/db/feedback_repo.py`). Verified by the integration test.

- [x] **2.12 Review queue + routing send**
  - Files: `app/feedback/review.py`, `app/api/routes_review.py`, `app/api/routes_routing.py`, `tests/test_review.py`
  - Accept: the queue combines gaps (and their routing) sorted pending-first; PATCH sets reviewed/resolved + note; `POST /api/routing/{id}/send` stores the edited question, status=sent (log only)
  - Verify: curl flow reject → send → `GET /api/review-queue` shows the item → `PATCH /api/review-queue/<id> -d '{"review_status":"reviewed","reviewer_note":"ok"}'`
  - Status: Done: `/api/review-queue` (+PATCH), `/api/routing/{id}/send` and `/dismiss` (log only). Verified by the integration test.

- [x] **2.13 Instrumentation**
  - Files: `app/observability/logging.py` (JSON logs), `app/observability/metrics.py`, `app/db/schema.sql` (+metrics), `app/api/routes_metrics.py`, `tests/test_metrics.py`
  - Accept: per-query metrics recorded; `GET /api/metrics` returns 24h/7d answer rate, routed rate, reject+correction rate, mean confidence, mean top score, citation validity, p95 latency, plus `alerts[]` when a value crosses an `ALERT_*` threshold or drops >X% vs the 7d baseline
  - Verify: fire about 10 queries, then `curl localhost:8000/api/metrics | jq`
  - Status: Done: `app/observability/metrics.py`; `/api/metrics?window=24h|7d|30d` with baseline comparison and alerts. JSON logging not added; standard logging with per-file progress lines.

- [~] **2.14 Golden eval set**
  - Files: `eval/golden.jsonl` (~20 questions → expected source files, written from the real data), `eval/run_eval.py`
  - Accept: reports hit@k, MRR, citation validity and answerability on unanswerable controls; non-zero exit below the target (used as a regression gate); calibrate `CONFIDENCE_THRESHOLD`
  - Verify: `uv run python -m eval.run_eval` prints the report; hit@5 ≥ 0.8
  - Status: In progress: `eval/golden.jsonl` (11 questions from one docx + 3 controls), runner in `app/evals/` (`uv run python -m app.evals`), synthetic generator. Synthetic run verified on demo data. Still open: the golden run on real data and threshold calibration.
  - Status (T3 run): **Pending:** extend the golden set across meetings/docx/pptx/xlsx, run it on real data, calibrate `CONFIDENCE_THRESHOLD`. Note: the Gemini free tier allows 15 requests/min per model (`LLM_MAX_RPM=14`), so a question takes about a minute.
  - Status (2026-10-06): F9 ran the golden eval on real data with Gemini (hit rate 1.0, faithfulness 1.0, relevance 1.0). Still open: extend the set beyond one docx, re-run it on the 40-file dataset, and calibrate `CONFIDENCE_THRESHOLD`.

- [x] **2.15 Ex2 smoke** ✅ CHECKPOINT
  - Files: `scripts/smoke_ex2.sh`
  - Accept: covers a meeting + office answer, citations with people, a low-confidence routing, reject, correct, gaps, review queue and metrics
  - Verify: `uv run pytest` && `./scripts/smoke_ex2.sh` green
  - Status: Done (on fixtures + mock Office files): `./scripts/smoke_ex2.sh` all checks passed against a live server, and the Ollama integration test passes. Re-run on real data with 1.10 / 2.4.
  - Status (T3 run): **Pending:** on real data it failed "every citation has source file + author" because `yield_tracker.xlsx` had no author; fixed in the data, re-run after the spreadsheet re-ingest.

---

## Exercise 3: Web application

- [x] **3.1 API client + layout**
  - Files: `src/types.ts`, `src/api/client.ts`, `src/App.tsx` (nav: Ask / Review Queue / Metrics), `src/main.tsx`
  - Accept: typed functions for every endpoint; simple tab/route navigation
  - Verify: `npm run build`; nav renders
  - Status: Done: `src/api/client.ts` (typed client + SSE parser), `src/types.ts`, `src/App.tsx` (nav: Chat, Documents, Review queue, Monitoring, Evals; dark mode).

- [x] **3.2 Ask page**
  - Files: `src/pages/AskPage.tsx`, `src/components/FilterBar.tsx`
  - Accept: query input, filters (topic, priority, source type), loading/error states
  - Verify: asking a question shows the response in the browser
  - Status: Done: implemented as a streaming Chat page (`src/pages/ChatPage.tsx`) with conversation history and filters.

- [x] **3.3 Answer with citations + metadata**
  - Files: `src/components/AnswerCard.tsx`, `CitationChip.tsx`, `SourceList.tsx`, `MetadataBadges.tsx`
  - Accept: every claim shows inline chips; hover/click shows file, location, author/attendees, snippet; badges for topic/priority/products/date; confidence indicator
  - Verify: in the browser, each claim has ≥1 chip showing file + person
  - Status: Done: inline citation chips with hover card + click-to-open document drawer with the chunk highlighted; metadata badges and confidence (`src/components/citations.tsx`, `chat.tsx`).

- [x] **3.4 Correct / reject**
  - Files: `src/components/CorrectionDialog.tsx`, `AnswerCard.tsx`
  - Accept: correct (text) and reject (reason) post to the API; a confirmation shows; reject reveals routing
  - Verify: the submission appears in `curl localhost:8000/api/gaps`
  - Status: Done: Correct / Reject dialogs plus thumbs up/down.

- [x] **3.5 Routing panel**
  - Files: `src/components/RoutingPanel.tsx`
  - Accept: shows who/role/why/matched sources; editable draft question; Send → log; sent state shown
  - Verify: edit + send → the routing status is `sent` in the API/review queue
  - Status: Done: routing panel with editable draft, Send (logged), Copy, Dismiss.

- [x] **3.6 Review queue page**
  - Files: `src/pages/ReviewQueuePage.tsx`
  - Accept: table of gaps/corrections/routings with the original query, answer, correction and sent question; filter by type/status; mark reviewed/resolved with a note
  - Verify: PATCH persists after a page refresh
  - Status: Done: `src/pages/ReviewPage.tsx` (counts, filters, expandable items, review/resolve/reopen with note).

- [x] **3.7 Metrics page**
  - Files: `src/pages/MetricsPage.tsx`
  - Accept: KPI tiles for 24h/7d + alert banners
  - Verify: values match `curl /api/metrics`
  - Status: Done: `src/pages/MonitoringPage.tsx` (alerts, KPI tiles vs previous window, trend charts).

- [x] **3.8 Measurement doc + README** ✅ CHECKPOINT
  - Files: `docs/MEASUREMENT.md`, `README.md`, `Makefile` (or `scripts/dev.sh`)
  - Accept: one-paragraph 30-day metric (proposed: verified-answer rate, from the queries/gaps tables with a weekly golden-set control); README covers setup, ingest, run both, smoke tests and a demo script
  - Verify: follow the README from a clean clone; the full demo flow works in the browser
  - Status: Done: `docs/MEASUREMENT.md`, root and backend READMEs, `dev.sh` starts both servers.

---

## Additional scope (requested during Exercise 3)

- [x] **E1 Conversational chat with SSE streaming**: `POST /api/chat/stream`, follow-up rewriting from history, conversations persisted in SQLite (`/api/conversations`)
- [x] **E2 Guardrails**: prompt-injection heuristics + LLM input classifier (off-topic / small talk), PII redaction on the token stream, grounding (uncited claims dropped)
- [x] **E3 Documents page + viewer**: list/search/filter, ingest button with report, viewer with metadata, chunks, business rules applied, original download
- [x] **E4 Evals page**: run golden/synthetic sets, generate a synthetic set, live progress, summary vs targets, per-case table, trend across runs
- [x] **E5 Monitoring page**: KPI tiles, alerts, trend charts (validated chart palette)
- [x] **E6 UI walkthrough**: Playwright run over every page on demo data, no console errors

---

## Additional scope (requested 2026-10-06)

- [x] **F1 README rewrite**
  - Files: `README.md`
  - Accept: clean, simple and informative, modelled on github.com/tanzeela-16/RAG_Chatbot_ComapnyDocs: one-line pitch, features table, architecture diagram + pipeline steps, quick start, tech stack, project structure, links to deeper docs
  - Verify: following the quick start from a clean clone runs the app
  - Status: Done: README follows the reference layout (features, architecture, quick start, pages, stack, structure, tests, docs).

- [x] **F2 Traceability page**
  - Files: `backend/app/api/routes_review.py` (or new route), `frontend/src/pages/TracePage.tsx`, `App.tsx`, `api/client.ts`, `types.ts`
  - Accept: a new menu entry lists answered questions; each trace shows the question → guardrail verdict → rewritten query → retrieved chunks with scores (semantic, BM25, fused, rerank) and which were cited → claims kept/dropped → confidence → status/routing/gaps/feedback
  - Verify: ask a question in Chat, open Trace, and see that query with its retrieved and cited documents
  - Status: Done: `GET /api/traces[/{id}]`, Traceability page with a 7-step lineage, *Trace* link on each answer; verified in the browser and `tests/test_upload_and_traces.py`.

- [x] **F3 Document upload**
  - Files: `backend/app/api/routes.py`, `frontend/src/pages/DocumentsPage.tsx`, `api/client.ts`, `CLAUDE.md` (data/ rule updated: UI uploads may write to `data/`)
  - Accept: the Documents page uploads a new or updated file (.md meeting, .docx/.pptx/.xlsx/.doc/.ppt/.xls); it is saved under `data/meetings/` or `data/documents/<ext>/` (same name = replace) and ingested; unsupported types and unsafe names are rejected
  - Verify: upload a file → it appears in the list with derived metadata; re-upload it changed → re-ingested, not duplicated
  - Status: Done: endpoint + Upload button; `tests/test_upload_and_traces.py` covers placement, replace, bad names/types. Real run: re-uploaded `meeting_2024_01_08_volta7_ramp_kickoff.md` unchanged → saved to `meetings/`, `replaced: true`, ingest 35 found / 0 ingested / 35 unchanged, file bytes and `data/` git status unchanged; `.exe` → 415. (That run predates the re-dating; the file is now `meeting_2026_01_05_volta7_ramp_kickoff.md`.)

- [x] **F4 About page**
  - Files: `frontend/src/pages/AboutPage.tsx`, `App.tsx`
  - Accept: explains what the system is, what it does (ingest → retrieve → cited answer → route → review → monitor) and how to use each page
  - Verify: `npm run build`; the page renders from the nav
  - Status: Done: `/about`, in the nav; `npm run build` passes; checked in the browser.

- [x] **F5 Chat layout does not jump when citations appear**
  - Files: `frontend/src/pages/ChatPage.tsx` / `components/chat.tsx`
  - Accept: the chat column keeps its position and width when the sources panel opens
  - Verify: ask a question; the message column doesn't shift left when sources arrive
  - Status: Done: the sources column is reserved from the start; Playwright measured the composer at the same x/width before, during and after an answer.

- [x] **F6 Clean `.env`**
  - Files: `backend/.env.example`, `backend/.env` (values kept), `backend/README.md`
  - Accept: the top section holds only what must be chosen (provider, model, key); all tuning is optional, commented out and defaults to `app/config.py`
  - Verify: `cp .env.example .env` + pick a preset → server starts; `uv run pytest -m "not integration"`
  - Status: Done: `.env.example` rewritten (one required preset + commented optional tuning); local `backend/.env` replaced with it on preset B (Ollama), old file kept as `backend/.env.bak`; every setting resolves to the same value as before.

- [x] **F7 DELIVERABLE.md**
  - Files: `DELIVERABLE.md`
  - Accept: every deliverable from the brief, how it is met and exactly where (files, endpoints, UI pages)
  - Verify: each requirement in `take-home-assignment.md` maps to a row
  - Status: Done: every requirement in the brief mapped to how it's met and where (files, endpoints, pages).

- [x] **F8 Data quality pass**
  - Files: `data/**` (user-approved), `backend/eval/golden.jsonl`, `backend/app/answer/guardrails.py`, `CLAUDE.md`
  - Accept: sources agree with each other (HTOL lot, Rev B reliability timeline, CMP fix date, mask list); text defects fixed; supply-chain and executive-strategy meetings and a company overview added; timeline moved to 2026 with weekdays preserved; "What does FastChip do?" gets a cited answer and "what is this system?" gets the assistant introduction
  - Verify: re-ingest reports 0 failures; `POST /api/query` "What does FastChip do?" cites `fastchip_company_overview.docx`; golden eval runs
  - Status: Done: re-ingest 40/40 with 0 failures (Ollama and Gemini); "What does FastChip do?" answers from `fastchip_company_overview.docx` (confidence 0.95); golden eval runs.

- [x] **F9 Flatten backend, fix dropped answers, honest faithfulness**
  - Files: `backend/app/*.py` (45 files in 12 folders → 15 modules), `backend/tests/`, `TECH.md`, docs
  - Accept: same API (29 paths) and tests; uncited but supported sentences are re-attached instead of dropped; questions about the assistant get the introduction; faithfulness judged per claim on full chunk text; runs on Gemini (`google_genai`)
  - Verify: `uv run pytest -m "not integration"`; "What does FastChip do?" cites `fastchip_company_overview.docx`; golden eval faithfulness ≥ 0.7
  - Status: Done: 15 modules, 41 unit tests, 29 API paths, smoke Ex1 9/9 and Ex2 12/12 on Gemini; golden eval faithfulness 1.0 (20/20 claims), hit rate 1.0, relevance 1.0. Answers that admit missing information are now capped at 0.45 so they route.

- [x] **F10 Workspace and setup polish** (requested 2026-10-06)
  - Files: `backend/pyproject.toml`, `backend/uv.lock`, `README.md`, `docs/MEASUREMENT.md`, `.claude/settings.json`, `.claude/skills/verify/SKILL.md`, `take-home-assignment.md`, `CLAUDE.md`, docs and memory
  - Accept:
    - Backend installs without PyTorch: `docling` → `docling-slim[convert-core,format-office,format-markdown]` (only Markdown/DOCX/PPTX/XLSX are parsed)
    - README lists the real system requirements (Python 3.12+, uv, **Node 20.19+ / 22.12+**, disk) and treats all providers equally, using tables and short steps
    - `MEASUREMENT.md` states one metric with a formula, a target and a check against missing feedback, in one paragraph
    - A ruff `PostToolUse` hook and a `/verify` skill package the Verify steps
    - Docs agree with the code and data: no stale module paths or 2024 dates, `take-home-assignment.md` labelled as the working spec over the PDF brief, dataset origin (generated outside this workspace) stated
  - Verify: `/verify` (lint, unit, Ollama integration, frontend build); re-parse all 40 files with docling-slim and compare with the stored content
  - Status: Done: backend install 1.5 GB → 625 MB; all 40 files parse to identical content; lint, 50 unit tests and the Ollama integration test pass; the hook was shown to reformat an edited file.

- [x] **F11 Committed seed index** (requested 2026-10-07)
  - Files: `backend/seed/` (`app.db`, `chroma/`, `README.md`), `.gitignore`, `backend/app/config.py` (`SEED_DIR`), `backend/app/main.py` (`seed_storage()`), `backend/tests/test_seed.py`, `backend/tests/conftest.py`
  - Accept: the shared workspace includes the index for `data/` with no chat history, feedback, gaps, metrics or eval runs; a fresh checkout or container starts with it; existing local storage is never overwritten
  - Verify: `uv run pytest tests/test_seed.py`; start the server on empty storage → `/api/stats` shows 40 documents and 176 chunks, `POST /api/ingest` reports 40 unchanged, retrieval returns the HTOL sources
  - Status: Done: seed is 7.5 MB (Gemini collection only); 53 unit tests pass; the seeded server passed all three checks.

- [x] **F12 Docker image and Render blueprint** (requested 2026-10-07)
  - Files: `backend/app/main.py` (`mount_frontend()`), `backend/app/config.py` (`FRONTEND_DIST`), `backend/tests/test_frontend_serving.py`, `Dockerfile`, `.dockerignore`, `render.yaml`, `README.md` (Run with Docker)
  - Accept: one container serves API + UI on `$PORT` as a non-root user; no secrets or local storage in the image; starts from the seed index; fits Render's free tier (512 MB); local `./dev.sh` unchanged
  - Verify: `uv run pytest -m "not integration"`; `docker build`; `docker run -m 512m` → `/`, `/review` and `/api/stats` (40 documents, 176 chunks); `smoke_ex1.sh` + `smoke_ex2.sh` against the container
  - Status: Done: 57 unit tests pass; container ready in ~2 s, 130 MB idle and 262 MB peak; both smoke suites pass. Found along the way: a Gemini free-tier 429 (rate limit) surfaces as HTTP 500; the re-run passed once the per-minute quota reset. Docker's `--env-file` keeps inline `# comments`, so the README mounts `.env` instead.

---

## Backlog

- [ ] **B1 Ingestion progress visibility**
  - Problem: `POST /api/ingest` blocks until the whole run finishes, and the server log shows little per file, so there's no way to see progress during a long run (enrichment + embedding of 20+ files).
  - Input: 1.6 pipeline, 1.8 API
  - Files: `app/ingestion/pipeline.py` (progress callback + per-file log lines), `app/ingestion/jobs.py` (new: in-memory job registry), `app/api/routes.py`, `app/models/api.py`, `app/ingestion/__main__.py`, `tests/test_ingest_progress.py`
  - Accept:
  - Status: Partial: per-file `[i/N]` log lines exist; the job status API and UI progress are still to do.
    - Server log prints one line per file and stage, e.g. `[3/20] meeting_x.md: enriching… chunked (4) embedded ✓ 6.2s`
    - `POST /api/ingest` returns a `job_id` right away (202) and runs in the background; `?wait=true` keeps the current blocking behaviour for scripts
    - `GET /api/ingest/{job_id}` (and `GET /api/ingest/latest`) returns status (`running|completed|failed`), `processed/total`, current file and stage, elapsed time, ETA, and the partial report (ingested/skipped/failed)
    - CLI shows a live per-file progress line
    - Exercise 3 UI can poll the status endpoint to show a progress bar
  - Verify: start an ingest with `{"force": true}`, poll `curl localhost:8000/api/ingest/latest | jq` and watch `processed` climb to `total`; the log shows per-file lines; `uv run pytest tests/test_ingest_progress.py`

- [ ] **B2 Infer metadata filters from the question (self-query)**
  - Problem: pre-filtering only applies when the caller sends `filters` explicitly. "What did Lisa say about yield in January 2024?" searches all meetings instead of Lisa's January yield meetings.
  - Input: 1.7 pre-filtering (`plan_filters()` in `app/retrieval/hybrid.py`, `repository.find_doc_ids()`)
  - Files: `app/retrieval/filter_extraction.py` (new), `app/retrieval/hybrid.py`, `app/models/api.py`, `app/config.py`, `tests/test_filter_extraction.py`
  - Accept:
    - An LLM structured-output step pulls `topic_domain`, `priority`, `person`, `date_from`/`date_to` out of the question (relative dates like "January" resolved against the corpus date range)
    - Guardrails: a person is kept only if it matches a known attendee in SQLite; topic/priority only if they're valid enum values; if the inferred filters match zero documents, fall back to an unfiltered search instead of returning nothing
    - Explicit `filters` in the request always win over inferred ones
    - Config `INFER_FILTERS=true|false` (default true) plus per-request `"infer_filters": false`
    - Response includes `retrieval.applied_filters` and `retrieval.filters_source` (`explicit|inferred|none`), so the UI can show and clear inferred filters
  - Verify: `uv run pytest tests/test_filter_extraction.py`; `curl -XPOST localhost:8000/api/query -d '{"query":"What did Lisa say in January 2024?"}'` shows `applied_filters.person` = "Lisa Park" and only her meetings in `results`; a question naming an unknown person returns unfiltered results with `filters_source: "none"`
  - Note (2026-10-06): the dataset is now dated 2026, so use "January 2026" in the examples above.

---

## Flags / decisions still open
1. `data/meetings/` is partly present. The real transcripts reference products and people (e.g. Volta-7) that differ from the brief's Eagle-5/Falcon-7 context. The enrichment prompt is product-agnostic, but CLAUDE.md's company context should be reconciled once the dataset is final.
2. Legacy `.doc/.ppt/.xls`: the LibreOffice shim is acceptable? (The dataset has none.)
3. Office author metadata: verify core properties are populated when the data arrives.
4. Business rules (2.5) are proposed, not specified by the brief. Confirm or adjust.
5. No auth: `submitted_by`/reviewer are free text.
6. Pinned Python 3.12 (the system has 3.13) for chromadb wheel safety.
7. `OPENAI_API_KEY` needed for real ingestion, querying and eval; tests run offline.

Status of the flags (2026-10-06):
- 1: resolved. The dataset is final (24 meetings + 16 documents); `fastchip_company_overview.docx` ties Volta-7 to the brief's company, and routing uses the people parsed from the data.
- 3: resolved. Core properties (author, title, date) are populated in all Office files and parsed by the loader.
- 7: superseded. Any LangChain provider works (OpenAI, Gemini, Ollama, …); tests run against real local Ollama, not offline fakes.
