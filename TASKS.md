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

## Exercise 1: Meetings → enrichment → query API

- [ ] **1.1 Config + model factory**
  - Input: 0.2
  - Files: `app/config.py`, `app/llm/factory.py`, `tests/test_factory.py`
  - Accept: all tunables in Settings (see CLAUDE.md); `get_llm()` / `get_embeddings()` honor the provider/model; fakes when `APP_ENV=test`; Chroma collection name gets the embedding model as a suffix
  - Verify: `uv run pytest tests/test_factory.py`

- [ ] **1.2 SQLite layer**
  - Input: 1.1
  - Files: `app/db/schema.sql` (documents, action_items, enrichment_cache), `app/db/sqlite.py`, `app/main.py` (lifespan init), `tests/test_db.py`
  - Accept: `init_db()` is idempotent; the connection helper returns rows as dicts
  - Verify: `uv run pytest tests/test_db.py`

- [ ] **1.3 Meeting loader**
  - Input: 1.2, `data/meetings/` present (inspect 2-3 real files before writing the parser)
  - Files: `app/models/source.py` (SourceDoc), `app/ingestion/loaders/meeting.py`, `app/ingestion/__main__.py` (`--dry-run`, `--only`), `tests/test_meeting_loader.py`
  - Accept: title, date and attendees parsed deterministically; body text preserved
  - Verify: `uv run pytest tests/test_meeting_loader.py`; `uv run python -m app.ingestion --dry-run --only meetings` lists 20 docs with attendees and dates

- [ ] **1.4 Enrichment chain**
  - Input: 1.3
  - Files: `app/models/enrichment.py`, `app/ingestion/enrich.py`, `tests/test_enrich.py`
  - Accept: `with_structured_output(EnrichmentResult)`; the prompt includes the company context and taxonomy; results cached by (content_hash, model); people never taken from the LLM
  - Verify: `uv run pytest tests/test_enrich.py`; manual: `uv run python -m app.ingestion --dry-run --only meetings --enrich --limit 1` prints valid enrichment JSON

- [ ] **1.5 Chunking + vector store**
  - Input: 1.1
  - Files: `app/ingestion/chunking.py`, `app/retrieval/vectorstore.py`, `tests/test_vectorstore.py`
  - Accept: RecursiveCharacterTextSplitter with configured size/overlap; flattened scalar metadata; `delete_by_doc_id` + upsert
  - Verify: `uv run pytest tests/test_vectorstore.py` (2 fixture docs, the search returns the right one)

- [ ] **1.6 Ingestion pipeline**
  - Input: 1.3-1.5
  - Files: `app/ingestion/pipeline.py`, `app/ingestion/__main__.py`, `tests/test_pipeline.py`
  - Accept: load → enrich → SQLite → chunk → Chroma; idempotent via content_hash; prints a summary (docs, chunks, enriched, skipped)
  - Verify: `uv run python -m app.ingestion --only meetings` → 20 docs; a rerun reports 0 re-enriched; `sqlite3 storage/app.db "select source_file, topic_domain, priority from documents"`

- [ ] **1.7 Retriever with filters**
  - Input: 1.6
  - Files: `app/retrieval/retriever.py`, `tests/test_retriever.py`
  - Accept: similarity search with relevance scores; filters on topic_domain, priority, source_type, person, date range; optional LLM extraction of filters from the NL query
  - Verify: `uv run pytest tests/test_retriever.py`; manual: "Eagle-5 yield issues" → top results from meetings 1-4

- [ ] **1.8 Query + ingest + documents API**
  - Input: 1.7
  - Files: `app/models/api.py`, `app/api/routes_query.py`, `app/api/routes_ingest.py`, `app/api/routes_documents.py`, `app/main.py`
  - Accept: `POST /api/query` returns a grounded answer + results with derived metadata (topic, priority, attendees, date, file); `POST /api/ingest`; `GET /api/documents` with filters
  - Verify:
    `curl -s -XPOST localhost:8000/api/query -H 'content-type: application/json' -d '{"query":"What is causing Eagle-5 yield loss?"}' | jq`
    `curl -s 'localhost:8000/api/documents?topic_domain=yield' | jq length`

- [ ] **1.9 Ex1 smoke + API tests** ✅ CHECKPOINT
  - Input: 1.8
  - Files: `scripts/smoke_ex1.sh`, `tests/test_api_ex1.py`
  - Accept: the script exercises health, ingest, query and documents and fails on a non-200 or missing fields
  - Verify: `uv run pytest`; `./scripts/smoke_ex1.sh` green against a live server

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

## Flags / decisions still open
1. `data/` isn't in the repo yet. It's needed from task 1.3 (meetings) and 2.1 (documents).
2. Legacy `.doc/.ppt/.xls`: the LibreOffice shim is acceptable? (The dataset has none.)
3. Office author metadata: verify core properties are populated when the data arrives.
4. Business rules (2.5) are proposed, not specified by the brief. Confirm or adjust.
5. No auth: `submitted_by`/reviewer are free text.
6. Pinned Python 3.12 (the system has 3.13) for chromadb wheel safety.
7. `OPENAI_API_KEY` needed for real ingestion, querying and eval; tests run offline.
