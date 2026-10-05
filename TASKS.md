# TASKS

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

- [x] **1.8 API**
  - Files: `app/api/routes.py`, `app/answer/generate.py`, `app/answer/service.py`, `app/models/api.py`, `app/main.py`
  - Accept: `POST /api/ingest`, `POST /api/query` (answer with [n] citations + results + derived document metadata + retrieval stats), `GET /api/documents[/{id}]`, `GET /api/stats`, `GET /api/health`
  - Verify: `./scripts/smoke_ex1.sh` against a running server

- [x] **1.9 Ex1 smoke + tests** ✅ CHECKPOINT (verified on fixtures with Ollama)
  - Files: `scripts/smoke_ex1.sh`, `tests/conftest.py`, `tests/test_*.py`, `tests/fixtures/meetings/`
  - Verify: `uv run pytest` (17 unit + 1 Ollama integration) and the smoke script, all green

- [ ] **1.10 Real-data run** (when `data/meetings/` is complete)
  - Verify: `POST /api/ingest` → `files_found` = 20, `failed` = []; check `warnings` for files without attendee lists; spot-check `GET /api/documents` topics/priorities; run `./scripts/smoke_ex1.sh`

---

## Exercise 2: Office docs, traceability, routing, gaps, instrumentation

- [ ] **2.1 DOCX loader**
  - Input: 1.9, `data/documents/docx/`
  - Files: `app/ingestion/loaders/docx.py`, `tests/test_docx_loader.py` (fixture generated in the test)
  - Accept: paragraphs + tables as text; author from core_properties → body "Author:/Owner:" → "unknown"; date from core props
  - Verify: pytest; `uv run python -m app.ingestion --dry-run --only documents` lists 5 docx with authors

- [ ] **2.2 PPTX loader**
  - Files: `app/ingestion/loaders/pptx.py`, `tests/test_pptx_loader.py`
  - Accept: one section per slide (title, text, notes) with location `slide N`; author
  - Verify: pytest; dry-run lists 5 pptx

- [ ] **2.3 XLSX loader**
  - Files: `app/ingestion/loaders/xlsx.py`, `tests/test_xlsx_loader.py`
  - Accept: per sheet, rows rendered as `header: value` lines with location `Sheet!rows a-b`; creator as author
  - Verify: pytest; dry-run lists 5 xlsx

- [ ] **2.4 Legacy formats + unified pipeline**
  - Files: `app/ingestion/loaders/legacy.py`, `app/ingestion/loaders/__init__.py` (extension registry), `app/ingestion/pipeline.py`, `app/ingestion/chunking.py` (keep location metadata)
  - Accept: `.doc/.ppt/.xls` converted with `soffice --headless --convert-to` if available, else skipped with a warning; all types share one SourceDoc/enrichment path
  - Verify: `uv run python -m app.ingestion` → 35 docs; `curl -s 'localhost:8000/api/documents?source_type=xlsx' | jq length` → 5

- [ ] **2.5 Business rules**
  - Files: `app/answer/business_rules.py`, `tests/test_business_rules.py`, hook into `enrich.py`
  - Accept: (a) people only from source; (b) claims without valid citations dropped; (c) priority escalated to critical for customer escalation / AEC-Q100 or safety / line-down; (d) one taxonomy across types; (e) newer source preferred on conflict, conflict surfaced
  - Verify: `uv run pytest tests/test_business_rules.py`

- [ ] **2.6 Cited answer chain**
  - Files: `app/answer/generate.py`, `app/answer/citations.py`, `tests/test_answer.py`, `app/api/routes_query.py`
  - Accept: the LLM returns `claims[{text, citations[n]}]` + an answerability score; the validator drops claims citing unknown chunks; every citation carries source_file, source_type, location, authors/attendees, date, snippet, score
  - Verify: pytest; the curl query shows every claim with ≥1 citation that has source_file + a person

- [ ] **2.7 Confidence scoring**
  - Files: `app/answer/confidence.py`, `tests/test_confidence.py`
  - Accept: weighted score from top/mean retrieval score, citation coverage and LLM answerability; `confident = score >= CONFIDENCE_THRESHOLD`
  - Verify: pytest; `curl ... -d '{"query":"What is on the cafeteria menu?"}'` → `confident:false`

- [ ] **2.8 Query logging**
  - Files: `app/db/schema.sql` (+queries), `app/feedback/queries.py`, `app/api/routes_query.py` (`GET /api/query/{id}`)
  - Accept: every query is persisted; the response includes `query_id`
  - Verify: POST a query, then `curl localhost:8000/api/query/<id>` returns the same answer

- [ ] **2.9 Routing engine**
  - Files: `app/routing/people.py`, `app/routing/router.py`, `app/db/schema.sql` (+routing_suggestions), `tests/test_router.py`
  - Accept: candidates from authors, attendees and action-item owners of retrieved docs, scored by retrieval relevance and enriched with role/dept; `reason` names the matched files and snippets; LLM-drafted question addressed to that person; persisted
  - Verify: pytest; a query like "What is the Falcon-7 thermal margin at 150°C junction?" returns routing to the relevant design/test people with file-based reasons

- [ ] **2.10 Low-confidence routing + reject**
  - Files: `app/db/schema.sql` (+gaps), `app/feedback/gaps.py`, `app/api/routes_query.py` (`POST /api/query/{id}/reject`)
  - Accept: a low-confidence query → routing in the response + a `low_confidence` gap; reject → a `rejected` gap + routing returned; query status updated
  - Verify: `curl -XPOST localhost:8000/api/query/<id>/reject -d '{"reason":"wrong lot","submitted_by":"me"}' -H 'content-type: application/json'`, then `curl localhost:8000/api/gaps`

- [ ] **2.11 Corrections + gaps API**
  - Files: `app/api/routes_gaps.py`, `app/api/routes_query.py` (`/correct`), `tests/test_gaps.py`
  - Accept: a correction stored with the original query, answer and citations; `GET /api/gaps?type=&status=`, `GET /api/gaps/{id}`
  - Verify: pytest; curl correct → it appears in `/api/gaps?type=correction`

- [ ] **2.12 Review queue + routing send**
  - Files: `app/feedback/review.py`, `app/api/routes_review.py`, `app/api/routes_routing.py`, `tests/test_review.py`
  - Accept: the queue combines gaps (and their routing) sorted pending-first; PATCH sets reviewed/resolved + note; `POST /api/routing/{id}/send` stores the edited question, status=sent (log only)
  - Verify: curl flow reject → send → `GET /api/review-queue` shows the item → `PATCH /api/review-queue/<id> -d '{"review_status":"reviewed","reviewer_note":"ok"}'`

- [ ] **2.13 Instrumentation**
  - Files: `app/observability/logging.py` (JSON logs), `app/observability/metrics.py`, `app/db/schema.sql` (+metrics), `app/api/routes_metrics.py`, `tests/test_metrics.py`
  - Accept: per-query metrics recorded; `GET /api/metrics` returns 24h/7d answer rate, routed rate, reject+correction rate, mean confidence, mean top score, citation validity, p95 latency, plus `alerts[]` when a value crosses an `ALERT_*` threshold or drops >X% vs the 7d baseline
  - Verify: fire about 10 queries, then `curl localhost:8000/api/metrics | jq`

- [ ] **2.14 Golden eval set**
  - Files: `eval/golden.jsonl` (~20 questions → expected source files, written from the real data), `eval/run_eval.py`
  - Accept: reports hit@k, MRR, citation validity and answerability on unanswerable controls; non-zero exit below the target (used as a regression gate); calibrate `CONFIDENCE_THRESHOLD`
  - Verify: `uv run python -m eval.run_eval` prints the report; hit@5 ≥ 0.8

- [ ] **2.15 Ex2 smoke** ✅ CHECKPOINT
  - Files: `scripts/smoke_ex2.sh`
  - Accept: covers a meeting + office answer, citations with people, a low-confidence routing, reject, correct, gaps, review queue and metrics
  - Verify: `uv run pytest` && `./scripts/smoke_ex2.sh` green

---

## Exercise 3: Web application

- [ ] **3.1 API client + layout**
  - Files: `src/types.ts`, `src/api/client.ts`, `src/App.tsx` (nav: Ask / Review Queue / Metrics), `src/main.tsx`
  - Accept: typed functions for every endpoint; simple tab/route navigation
  - Verify: `npm run build`; nav renders

- [ ] **3.2 Ask page**
  - Files: `src/pages/AskPage.tsx`, `src/components/FilterBar.tsx`
  - Accept: query input, filters (topic, priority, source type), loading/error states
  - Verify: asking a question shows the response in the browser

- [ ] **3.3 Answer with citations + metadata**
  - Files: `src/components/AnswerCard.tsx`, `CitationChip.tsx`, `SourceList.tsx`, `MetadataBadges.tsx`
  - Accept: every claim shows inline chips; hover/click shows file, location, author/attendees, snippet; badges for topic/priority/products/date; confidence indicator
  - Verify: in the browser, each claim has ≥1 chip showing file + person

- [ ] **3.4 Correct / reject**
  - Files: `src/components/CorrectionDialog.tsx`, `AnswerCard.tsx`
  - Accept: correct (text) and reject (reason) post to the API; a confirmation shows; reject reveals routing
  - Verify: the submission appears in `curl localhost:8000/api/gaps`

- [ ] **3.5 Routing panel**
  - Files: `src/components/RoutingPanel.tsx`
  - Accept: shows who/role/why/matched sources; editable draft question; Send → log; sent state shown
  - Verify: edit + send → the routing status is `sent` in the API/review queue

- [ ] **3.6 Review queue page**
  - Files: `src/pages/ReviewQueuePage.tsx`
  - Accept: table of gaps/corrections/routings with the original query, answer, correction and sent question; filter by type/status; mark reviewed/resolved with a note
  - Verify: PATCH persists after a page refresh

- [ ] **3.7 Metrics page**
  - Files: `src/pages/MetricsPage.tsx`
  - Accept: KPI tiles for 24h/7d + alert banners
  - Verify: values match `curl /api/metrics`

- [ ] **3.8 Measurement doc + README** ✅ CHECKPOINT
  - Files: `docs/MEASUREMENT.md`, `README.md`, `Makefile` (or `scripts/dev.sh`)
  - Accept: one-paragraph 30-day metric (proposed: verified-answer rate, from the queries/gaps tables with a weekly golden-set control); README covers setup, ingest, run both, smoke tests and a demo script
  - Verify: follow the README from a clean clone; the full demo flow works in the browser

---

## Backlog

- [ ] **B1 Ingestion progress visibility**
  - Problem: `POST /api/ingest` blocks until the whole run finishes, and the server log shows little per file, so there's no way to see progress during a long run (enrichment + embedding of 20+ files).
  - Input: 1.6 pipeline, 1.8 API
  - Files: `app/ingestion/pipeline.py` (progress callback + per-file log lines), `app/ingestion/jobs.py` (new: in-memory job registry), `app/api/routes.py`, `app/models/api.py`, `app/ingestion/__main__.py`, `tests/test_ingest_progress.py`
  - Accept:
    - Server log prints one line per file and stage, e.g. `[3/20] meeting_x.md: enriching… chunked (4) embedded ✓ 6.2s`
    - `POST /api/ingest` returns a `job_id` right away (202) and runs in the background; `?wait=true` keeps the current blocking behaviour for scripts
    - `GET /api/ingest/{job_id}` (and `GET /api/ingest/latest`) returns status (`running|completed|failed`), `processed/total`, current file and stage, elapsed time, ETA, and the partial report (ingested/skipped/failed)
    - CLI shows a live per-file progress line
    - Exercise 3 UI can poll the status endpoint to show a progress bar
  - Verify: start an ingest with `{"force": true}`, poll `curl localhost:8000/api/ingest/latest | jq` and watch `processed` climb to `total`; the log shows per-file lines; `uv run pytest tests/test_ingest_progress.py`

---

## Flags / decisions still open
1. `data/meetings/` is partly present. The real transcripts reference products and people (e.g. Volta-7) that differ from the brief's Eagle-5/Falcon-7 context. The enrichment prompt is product-agnostic, but CLAUDE.md's company context should be reconciled once the dataset is final.
2. Legacy `.doc/.ppt/.xls`: the LibreOffice shim is acceptable? (The dataset has none.)
3. Office author metadata: verify core properties are populated when the data arrives.
4. Business rules (2.5) are proposed, not specified by the brief. Confirm or adjust.
5. No auth: `submitted_by`/reviewer are free text.
6. Pinned Python 3.12 (the system has 3.13) for chromadb wheel safety.
7. `OPENAI_API_KEY` needed for real ingestion, querying and eval; tests run offline.
