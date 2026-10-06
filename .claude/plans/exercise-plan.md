# Plan: FastChip Knowledge RAG System (Teradyne take-home)

> **Snapshot:** the initial plan from plan mode, before `data/` existed, kept as written at the time. It is superseded by [`CLAUDE.md`](../../CLAUDE.md), [`TECH.md`](../../TECH.md) and [`TASKS.md`](../../TASKS.md). Later decisions changed parts of it: fake test models were rejected (tests use real local Ollama), the backend was flattened into one module per concern, and the dataset centres on Volta-7 rather than Eagle-5/Falcon-7.

## Context
The repo is empty apart from `take-home-assignment.md`, and `data/` doesn't exist yet (the user will add it). The goal is a RAG system for the fictional FastChip Semiconductor. It has three parts:
- **Ex1:** ingest meeting transcripts, enrich them, and query them through an API.
- **Ex2:** add Office docs, plus traceability, routing, gap/correction capture and quality instrumentation.
- **Ex3:** a React UI with citations, a routing panel and a review queue, plus a one-paragraph measurement approach.

The user wants three things: a full CLAUDE.md, a scaffolded project, and a numbered task list (in `TASKS.md`). Each task should be one shot, list its files, have acceptance criteria and end with a verification step. Each exercise should leave a runnable checkpoint.

User decisions: **OpenAI embeddings** are the default (configurable). Routing **"Send" only logs**. Enrichment uses **LLM structured output** (Pydantic + `with_structured_output`). Attendees, date and author are always parsed deterministically and never come from the LLM.

## What gets produced right after approval (Task 0.x)
1. `CLAUDE.md`, which holds all the context: company, people, dataset layout, stack, rules, schemas, API, folder structure, commands, and the conventions "never modify data/" and "mark tasks done in TASKS.md after verification".
2. `TASKS.md`, the numbered task list below, with `- [ ]` checkboxes plus Files / Acceptance / Verify for each task.
3. A scaffold: the `backend/` uv project, the `frontend/` Vite project, `.env.example`, `.gitignore`, `git init`.

## Architecture
```
data/ ──► loaders (md/docx/pptx/xlsx) ──► SourceDoc (text + deterministic meta: path, type, author/attendees, date, title)
                │
                ├─► enrichment chain (gpt-4o-mini, Pydantic) ──► topic_domain, priority, products, summary, decisions, action_items
                │        (cached in SQLite by content hash)
                ├─► SQLite: documents, action_items (structured, queryable)
                └─► splitter ──► ChromaDB chunks (metadata flattened: doc_id, source_file, source_type, authors, topic_domain, priority, location e.g. slide/sheet)

POST /api/query ─► retriever (similarity + optional metadata filters) ─► answer chain (claims[] each w/ citation ids)
                 ─► citation validator ─► confidence scorer ─► business rules
                 ─► confident? answer+citations+metadata : routing engine (who/why/draft question)
                 ─► log to queries + metrics tables
```
- **Configurable everything:** `app/config.py` uses pydantic-settings over `.env`. It covers `LLM_PROVIDER`, `LLM_MODEL`, `LLM_TEMPERATURE`, `EMBEDDING_PROVIDER` (openai|huggingface), `EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `CONFIDENCE_THRESHOLD`, `MIN_RETRIEVAL_SCORE`, `CHROMA_DIR`, `CHROMA_COLLECTION`, `SQLITE_PATH`, `DATA_DIR` and `CORS_ORIGINS`. `app/llm/factory.py` provides `get_llm()` and `get_embeddings()`, and nothing else constructs models directly.
- **Changing the embedding model** requires a re-index. The Chroma collection name gets the model as a suffix, so mismatched vectors can never mix.
- **Tests run offline.** They use LangChain `FakeListChatModel` and `DeterministicFakeEmbedding`, injected through the factory when `APP_ENV=test`.

## Folder structure
```
backend/
  pyproject.toml  .env.example
  app/
    main.py                 # FastAPI app, routers, CORS, lifespan (init db)
    config.py
    llm/factory.py
    db/sqlite.py  db/schema.sql
    models/                 # Pydantic: source.py, enrichment.py, api.py
    ingestion/
      loaders/{meeting,docx,pptx,xlsx,legacy}.py
      enrich.py  chunking.py  pipeline.py  __main__.py  (uv run python -m app.ingestion)
    retrieval/vectorstore.py  retriever.py
    answer/generate.py  citations.py  confidence.py  business_rules.py
    routing/people.py  router.py
    feedback/gaps.py  review.py
    observability/metrics.py  logging.py
    api/routes_{health,ingest,query,gaps,review,metrics,documents}.py
  eval/golden.jsonl  eval/run_eval.py
  scripts/smoke_ex1.sh  smoke_ex2.sh
  tests/ (fixtures/ with tiny md/docx/pptx/xlsx generated in conftest, not in data/)
frontend/  (Vite + React + TS + Tailwind)
  src/api/client.ts  src/types.ts
  src/pages/{AskPage,ReviewQueuePage,MetricsPage}.tsx
  src/components/{AnswerCard,CitationChip,SourceList,MetadataBadges,RoutingPanel,CorrectionDialog,FilterBar}.tsx
docs/MEASUREMENT.md
data/  (user-provided, read-only)
```

## SQLite schema (summary)
- `documents`: id, source_file, source_type, title, date, authors_json, attendees_json, content_hash, topic_domain, priority, products_json, summary, decisions_json, enrichment_json, ingested_at
- `action_items`: id, document_id, owner, task, due_date
- `queries`: id, query_text, filters_json, answer, claims_json, citations_json, confidence, status (answered|routed|rejected|corrected), latency_ms, created_at
- `routing_suggestions`: id, query_id, person, role, reason, matched_sources_json, draft_question, edited_question, status (suggested|sent|dismissed), sent_at
- `gaps`: id, query_id, type (low_confidence|rejected|correction), original_answer, correction_text, submitted_by, review_status (pending|reviewed|resolved), reviewer_note, created_at, reviewed_at
- `metrics`: id, query_id, top_score, mean_score, n_citations, citation_valid_ratio, confidence, latency_ms, tokens_in, tokens_out, created_at
- `enrichment_cache`: content_hash, model, enrichment_json

## API
`GET /api/health` · `POST /api/ingest` · `GET /api/documents` (filter by topic/priority/type/person) · `POST /api/query` · `GET /api/query/{id}` · `POST /api/query/{id}/correct` · `POST /api/query/{id}/reject` · `POST /api/routing/{id}/send` (edited question, log only) · `GET /api/gaps` (?type,status) · `GET /api/gaps/{id}` · `GET /api/review-queue` · `PATCH /api/review-queue/{id}` · `GET /api/metrics` (rolling windows + alerts)

`POST /api/query` returns `{query_id, answer, claims:[{text, citations:[n]}], citations:[{n, source_file, source_type, location, authors|attendees, date, snippet, score}], results_metadata:[{topic_domain, priority, products,...}], confidence, confident:bool, routing?:[{person, role, reason, matched_sources, draft_question, routing_id}]}`

---

## Task list (goes into TASKS.md)
Every task ends with **Verify**. Mark `[x]` only after verification passes.

### Phase 0: Setup
- **0.1** Write CLAUDE.md + TASKS.md, `git init`, `.gitignore`. *Verify:* files exist and `git status` is clean after the first commit.
- **0.2** Backend scaffold: `uv init`, Python 3.12, deps (fastapi, uvicorn, langchain, langchain-openai, langchain-chroma, langchain-huggingface[optional extra], chromadb, pydantic-settings, python-docx, python-pptx, openpyxl, python-frontmatter, structlog; dev: pytest, httpx, ruff), skeleton `app/main.py` with `/api/health`. *Verify:* `uv run uvicorn app.main:app` then `curl localhost:8000/api/health` returns `{"status":"ok"}`; `uv run pytest` and `uv run ruff check` pass.
- **0.3** Frontend scaffold: Vite React-TS + Tailwind, a `/api` proxy to :8000, a placeholder page that calls health. *Verify:* `npm run dev` shows "backend: ok"; `npm run build` passes.

### Exercise 1: Meetings → enrichment → query API
- **1.1** `config.py` + `llm/factory.py` (openai/hf embeddings, fake models in test). *Verify:* pytest checks that the factory returns the configured classes and that an env override changes the model.
- **1.2** SQLite layer: `schema.sql` (documents, action_items, enrichment_cache), connection helper, init on startup. *Verify:* pytest creates a temp DB and asserts the tables exist.
- **1.3** Meeting loader: parse title/date/attendees (frontmatter or header lines; inspect real files first) → `SourceDoc`. *Verify:* pytest on fixtures; `uv run python -m app.ingestion --dry-run --only meetings` prints 20 docs with attendees and dates.
- **1.4** Enrichment chain: `EnrichmentResult` Pydantic model (topic_domain enum, priority enum, products, summary, decisions, action_items) with a prompt holding the company context, plus a content-hash cache. *Verify:* pytest with a fake LLM; a manual run on one real transcript prints valid JSON.
- **1.5** Chunking + Chroma wrapper (upsert by doc_id, delete-on-reingest, flattened metadata). *Verify:* pytest indexes 2 fixture docs and a similarity search returns the right one.
- **1.6** Ingestion pipeline + CLI (idempotent via content_hash; summary report). *Verify:* `uv run python -m app.ingestion` gives 20 documents in SQLite and N chunks in Chroma; a rerun re-enriches 0 docs.
- **1.7** Retriever with filters (topic_domain, priority, source_type, person, date range) + optional LLM filter extraction from the NL query. *Verify:* pytest; for "Eagle-5 yield issues" the top results are meetings 1-4.
- **1.8** API: `POST /api/ingest`, `POST /api/query` (results + derived metadata + concise grounded answer), `GET /api/documents`. *Verify:* curl both; the response contains attendees and topic/priority.
- **1.9** `scripts/smoke_ex1.sh` + API tests (TestClient, fakes). *Verify:* the script runs green against a live server. **Checkpoint Ex1.**

### Exercise 2: Office docs, traceability, routing, gaps, instrumentation
- **2.1** DOCX loader (python-docx text + tables; author from core_properties, falling back to an "Author:/Owner:" line in the body). *Verify:* pytest on a generated fixture; dry-run lists 5 docx with authors.
- **2.2** PPTX loader (per-slide text + notes, location=`slide N`, author). *Verify:* same pattern, 5 pptx.
- **2.3** XLSX loader (per-sheet, rows rendered as `header: value` lines, location=`sheet/rows`, creator). *Verify:* same pattern, 5 xlsx.
- **2.4** Legacy `.doc/.ppt/.xls` shim (LibreOffice `soffice --convert-to` if available, else skip with a warning) + register all loaders in the pipeline with a unified metadata model. *Verify:* full ingest gives 35 documents; `GET /api/documents?source_type=xlsx` returns 5.
- **2.5** `business_rules.py`: one module applied at ingest and query time (see Gaps for the proposed rules). *Verify:* unit tests per rule.
- **2.6** Answer chain with per-claim citations + `citations.py` validator (drops claims citing chunks that weren't retrieved; every citation resolves to file + author/attendees). *Verify:* pytest; a real curl shows each claim with ≥1 citation with source_file and person.
- **2.7** `confidence.py`: combines top/mean retrieval score, citation coverage and LLM self-rated answerability → `confident` at `CONFIDENCE_THRESHOLD`. *Verify:* pytest; an off-topic query ("cafeteria menu") gives confident=false.
- **2.8** Query logging (`queries` table), `query_id` in the response, `GET /api/query/{id}`. *Verify:* curl the query, then GET by id.
- **2.9** Routing engine: `people.py` directory (names/roles/dept from CLAUDE.md context), ranking of candidates from authors/attendees/action-item owners weighted by retrieval score, `reason` built from matched files/snippets, LLM-drafted question; persisted to `routing_suggestions`. *Verify:* pytest; "Falcon-7 thermal margin at 150°C" suggests Priya Patel or the relevant author, with reasons citing files.
- **2.10** Wire routing into low-confidence queries (auto-create a `low_confidence` gap) + `POST /api/query/{id}/reject` (creates a gap + returns routing). *Verify:* curl reject; the gap appears.
- **2.11** `POST /api/query/{id}/correct` + `GET /api/gaps`, `GET /api/gaps/{id}` (stores the original query + answer + correction). *Verify:* curl correct, then list gaps.
- **2.12** Review queue `GET/PATCH /api/review-queue` + `POST /api/routing/{id}/send` (log only, status=sent). *Verify:* curl the full flow: reject → send → queue shows the item → PATCH reviewed.
- **2.13** Instrumentation: `metrics` table per query, JSON structured logs, `GET /api/metrics` (rolling 24h/7d: answer rate, routed rate, rejection/correction rate, mean confidence, citation validity, p95 latency) with alert flags against configured thresholds/baseline. *Verify:* fire 10 queries, then curl metrics shows non-zero windows and alerts evaluate.
- **2.14** Golden eval set (~20 Q→expected source files, written after reading the data) + `eval/run_eval.py` (hit@k, citation validity, answerability). It's runnable as a regression gate. *Verify:* `uv run python -m eval.run_eval` prints a report with hit@5 ≥ target.
- **2.15** `scripts/smoke_ex2.sh` covering both sources, traceability, routing and gaps. *Verify:* green. **Checkpoint Ex2.**

### Exercise 3: Web app
- **3.1** Typed API client + types matching the backend models; app layout with nav (Ask / Review Queue / Metrics). *Verify:* `npm run build`; the nav renders.
- **3.2** Ask page: query box, FilterBar (topic, priority, source type), loading/error states. *Verify:* a query shows the raw response.
- **3.3** AnswerCard: claims with inline CitationChips (hover/click shows file, location, author/attendees, snippet), SourceList, MetadataBadges (topic, priority, products, date). *Verify:* in the browser, every claim shows a chip with file + person.
- **3.4** Correct / Reject actions (CorrectionDialog). *Verify:* the submission appears in `GET /api/gaps`.
- **3.5** RoutingPanel shown when not confident or after a reject: who/role/why/matched sources and an editable draft question; Send (log). *Verify:* edit + send; the routing status is `sent` in the API.
- **3.6** Review Queue page: table of gaps/corrections/routings, filter by status/type, mark reviewed with a note. *Verify:* PATCH reflects in the UI after refresh.
- **3.7** Metrics page (KPI tiles + alert banners from `/api/metrics`). *Verify:* values match curl.
- **3.8** `docs/MEASUREMENT.md` (one paragraph: the 30-day metric, e.g. **verified-answer rate** = answered queries not rejected/corrected within the session ÷ total queries, measured from the `queries`/`gaps` tables with weekly golden-set eval as a control). Root README with run instructions; `make dev` or scripts to start both. *Verify:* follow the README from a clean clone. **Checkpoint Ex3.**

---

## Gaps / decisions flagged
1. **`data/` isn't present yet.** Task 1.3 inspects the real transcript format before writing the parser; tests use self-generated fixtures under `tests/`.
2. **Legacy `.doc/.ppt/.xls`:** required by the spec, but the dataset only has OOXML. Plan: a LibreOffice conversion shim with graceful skip. Confirm whether that's enough.
3. **Author metadata in the Office files:** if `core_properties.author` is empty or generic ("python-docx"), fall back to body text, else "unknown". Check this when the data arrives.
4. **"Business rules apply consistently"** is undefined in the spec. Proposed rules:
   - (a) people (attendees, authors) come only from source, never from the LLM
   - (b) every claim needs a valid citation or it's dropped
   - (c) priority=critical if a customer escalation, AEC-Q100/safety issue or line-down is involved
   - (d) the same topic_domain taxonomy for all source types
   - (e) the newest source wins when sources conflict, and the conflict is surfaced
5. **Confidence threshold** starts as a heuristic and gets calibrated against the golden set in 2.14.
6. **No auth:** `submitted_by` / reviewer is free text in the UI.
7. **People directory** for routing roles comes from the company context (config, not data generation).
8. **Python 3.12** is pinned via uv (the system has 3.13; 3.12 is safer for chromadb/torch wheels).
9. An `OPENAI_API_KEY` is required for real runs; tests don't need it.

## Verification (end-to-end)
- Backend: `cd backend && uv run pytest && uv run python -m app.ingestion && uv run uvicorn app.main:app --reload`, then `scripts/smoke_ex1.sh`, `scripts/smoke_ex2.sh`, `uv run python -m eval.run_eval`.
- Frontend: `cd frontend && npm run dev`. Ask "What caused the Eagle-5 yield drop and who owns the fix?" and check the claims have citations (file + person) and the metadata badges show. Ask an off-topic or unanswerable question and check the routing panel appears; edit and send it. Reject an answer and confirm it appears in the Review Queue; mark it reviewed.
