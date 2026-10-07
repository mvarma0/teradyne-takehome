# Deliverables

Each requirement from the brief ([`take-home-assignment.md`](take-home-assignment.md)), how it is met and exactly where. Paths are relative to the repo root; endpoints are served by `uv run uvicorn app.main:app` (from `backend/`) and the UI by `./dev.sh`.

**Status at a glance**

| # | Exercise | Deliverable | Status | Proof |
|---|---|---|---|---|
| 1 | Meeting transcripts | Working service callable via curl or a test script | ✅ Met | `backend/scripts/smoke_ex1.sh`, `POST /api/query` |
| 2 | Office documents | Both sources behind one API; traceability, routing and gap capture working | ✅ Met | `backend/scripts/smoke_ex2.sh` |
| 3 | User-facing app | Working local app + one-paragraph measurement approach | ✅ Met | `frontend/` (React), `docs/MEASUREMENT.md` |

---

## Exercise 1: Meeting transcripts

| Requirement | How it is met | Where |
|---|---|---|
| **Ingest** the transcript folder | Discovers `data/meetings/*.md`, parses each one, then enriches, chunks and stores it. Idempotent per content hash; deleted files are pruned | `backend/app/ingest.py` · `POST /api/ingest` · `uv run python -m app.ingest` · Documents page → *Ingest changes* |
| Derive **topic domain** | LLM structured output into a fixed enum (yield, design, test_engineering, npi_program, supply_chain, customer, quality_compliance, executive_strategy, other); cached by content hash + model + prompt version | `backend/app/ingest.py`, `backend/app/schemas.py` |
| Derive **priority** where applicable | LLM priority (critical…none), then a keyword priority floor (rule R1) applied the same way to every source type | `backend/app/ingest.py` (`enrich`), `backend/app/rules.py` (`apply_ingest_rules`) |
| **Attendees preserved exactly** | Parsed deterministically from the `Attendees:` header (names + roles), never from the LLM. Title, date, meeting type and location are parsed the same way | `backend/app/loaders.py` · test `backend/tests/test_meeting_loader.py` |
| Extra metadata | Products, summary, key topics, decisions, action items (owner/task/due). Owners and products must appear in the source (rules R2, R3) | `backend/app/ingest.py`, `backend/app/rules.py` |
| **Store** in a structured, queryable format | SQLite `documents` + `action_items` (canonical metadata), Chroma (chunk vectors + scalar metadata) | `backend/app/schema.sql`, `backend/app/db.py`, `backend/app/search.py` |
| **Query API**: natural-language query → relevant results with derived metadata | `POST /api/query` returns the answer, citations and each source's derived metadata. `generate_answer:false` returns retrieval only. Filters: topic, priority, source type, person, date range | `backend/app/api.py`, `backend/app/search.py` · `GET /api/documents` (metadata with filters) |
| Callable via **curl or a test script** | Smoke script plus unit tests and an end-to-end test against local Ollama | `backend/scripts/smoke_ex1.sh`, `backend/tests/` |

## Exercise 2: Office documents

| Requirement | How it is met | Where |
|---|---|---|
| Ingest **.doc/.docx, .ppt/.pptx, .xls/.xlsx** alongside transcripts | docling per section, slide (+ speaker notes) or sheet. Legacy formats are converted through LibreOffice if installed, otherwise reported as a clear failure. Non-OOXML files with an Office extension fall back to plain text | `backend/app/loaders.py` · test `backend/tests/test_office_and_rules.py` |
| **Single API** for both sources | One ingestion pipeline, one Chroma collection, one `documents` table, one query endpoint; `source_type` is just a filter | `backend/app/ingest.py` (`run_ingestion`), `POST /api/query`, `POST /api/chat/stream` |
| **Business rules applied consistently** | All rules live in one module and are applied identically at ingest (R1-R3) and answer time (R5 uncited claims dropped, R6 newest source wins on conflict) for every source type | `backend/app/rules.py`, `backend/app/answer.py` |
| **Traceability**: every fact → source file + author/attendees | Every citation carries `source_file`, `section`, `date`, `people` + `people_label` (Attendees or Author). Authors come from core properties or body bylines (`**Author:** Name, Role`), never the LLM. Claims without a valid citation are dropped | `backend/app/loaders.py` (`load_office`), `backend/app/answer.py` (`citation_payload`, `build_claims`) |
| Traceability of a whole answer | `GET /api/traces/{id}` returns the full lineage: question, guardrail verdict, rewritten query, retrieved chunks with semantic/BM25/fused/rerank scores, which were cited, kept and dropped claims, confidence components, status, routing, gaps and feedback | `backend/app/api.py`, `backend/app/db.py` (`list_traces`) · UI **Traceability** page |
| **Routing**: who to ask | Candidates are the attendees, authors, reviewers and action-item owners of the retrieved sources, weighted by each source's retrieval rank and rerank score | `backend/app/feedback.py` (`rank_people`, `suggest_routing`) |
| Routing: **why** | A reason plus the matched sources (file, date, snippet) per person | `backend/app/feedback.py` (`_reason`), `matched_sources` in the payload |
| Routing: **drafted question** | LLM-drafted question per person (template fallback); editable and logged on send | `backend/app/feedback.py` (`suggest_routing`), `POST /api/routing/{id}/send`, `/dismiss` |
| When routing triggers | Confidence (retrieval + rerank + citation coverage) below `CONFIDENCE_THRESHOLD`, or the user rejects an answer | `backend/app/answer.py`, `backend/app/feedback.py` (`reject`) |
| **Corrections and rejections captured with the original query** | Each one creates a `gaps` row holding the query text, the original answer, the correction or reason, and who submitted it; low-confidence answers create gaps automatically | `backend/app/feedback.py` (`correct`, `reject`), `backend/app/db.py` · `POST /api/query/{id}/correct`, `/reject` |
| **Gap retrieval through the API** | List with type and status filters, single detail, review queue with counts, review/resolve with a note | `GET /api/gaps`, `GET /api/gaps/{id}`, `GET/PATCH /api/review-queue[/{id}]` in `backend/app/api.py` |
| **Instrumentation catches degradation before users notice** | One metrics row per answer (status, confidence, top scores, citation validity, uncited drops, PII, latency). Rollups compare the current window with the previous one and alert on absolute thresholds and on relative drops vs baseline. Golden + synthetic evals catch regressions offline before a change ships | `backend/app/metrics.py` · `GET /api/metrics?window=24h|7d|30d` · `ALERT_*` in `.env` · `backend/app/evals.py` · `/api/evals/*` |
| Working system over both sources | Curl checks for both sources, traceability, guardrails, routing, gaps, review and metrics | `backend/scripts/smoke_ex2.sh` |

## Exercise 3: User-facing application

| Requirement | How it is met | Where |
|---|---|---|
| Ask in plain language | Streaming multi-turn chat (SSE); follow-ups are rewritten with the history; optional filters | `frontend/src/pages/ChatPage.tsx`, `frontend/src/components/chat.tsx` (`Composer`), `POST /api/chat/stream` |
| **Visible citations: source file + author for each claim** | Inline numbered citation chips per claim; hover shows file, author or attendees, date and snippet; click opens the document with the passage highlighted. A sources rail lists every passage | `frontend/src/components/citations.tsx` (`CitationChip`, `EvidenceRail`, `DocumentDrawer`) |
| **Derived metadata alongside results** | Topic, priority and product badges plus a confidence meter under each answer; full metadata per source in the Documents viewer | `frontend/src/components/meta.tsx`, `chat.tsx` (`AnswerMeta`), `frontend/src/pages/DocumentViewerPage.tsx` |
| **Suggested routing to review, edit and send** | Routing panel per person: role, reason, matched files, editable draft, *Send* (logged), *Copy*, *Dismiss* | `chat.tsx` (`RoutingPanel`, `RoutingCard`) |
| Corrections and rejections from the UI | Thumbs up/down, *Correct* and *Reject* dialogs; rejecting reveals routing | `chat.tsx` (`FeedbackBar`) |
| **Simple review queue for a team lead** | Counts, type/status filters, each item with question, answer, correction, routing and sources; mark reviewed or resolved with a note | `frontend/src/pages/ReviewPage.tsx` |
| **Working application, runs locally (React preferred)** | React 19 + Vite + TypeScript + Tailwind; `./dev.sh` starts the backend and frontend | `frontend/`, `dev.sh`, [README quick start](README.md#-quick-start) |
| **Measurement approach: one 30-day metric, one paragraph** | Verified-answer rate: the share of knowledge questions answered confidently with valid citations and no pushback, computed from data the system already logs, with a weekly audit and eval control | [`docs/MEASUREMENT.md`](docs/MEASUREMENT.md) |

## Beyond the brief

| Addition | Where |
|---|---|
| Traceability page: question → retrieval → citations → confidence → routing/gaps | `frontend/src/pages/TracePage.tsx`, `GET /api/traces[/{id}]` (also linked from each answer via *Trace*) |
| Document upload: add or replace a source from the UI, then ingest changes | Documents page *Upload*, `POST /api/documents/upload` |
| About page explaining the system | `frontend/src/pages/AboutPage.tsx` |
| Guardrails: prompt injection, off-topic, PII redaction on the live stream | `backend/app/guardrails.py` |
| Hybrid retrieval with pointwise LLM rerank | `backend/app/search.py` |
| Monitoring dashboard and eval runner pages | `frontend/src/pages/MonitoringPage.tsx`, `EvalsPage.tsx` |
| Configurable providers (OpenAI, Gemini, Ollama, any LangChain provider) with no code change | `backend/app/llm.py`, `backend/.env.example` |

## Notes and deviations

- **Dataset vs brief:** the provided data centres on the Volta-7 controller and customer NovaDrive Motors. A company overview document places it in the brief's context (Eagle-5 and Falcon-7 product lines, the brief's leadership team, Austin / Portland / Penang sites). Prompts are product-agnostic, and routing uses the people parsed from the data.
- **Read-only data:** ingestion never changes `data/`. The one exception is the user-requested upload feature, which writes the file the user uploads (and replaces a same-named file). With user approval, the corpus also had one quality pass: spreadsheet properties added, cross-source contradictions fixed, supply-chain and strategy meetings plus a company overview added, and the timeline moved to 2026. Legacy `.doc/.ppt/.xls` support is implemented through LibreOffice but has no sample files, because LibreOffice isn't installed in this environment.
- **No auth:** `submitted_by`, reviewer and `sent_by` are free text, and routed questions are logged, not delivered.
- **Confidence threshold** (0.55) is calibrated on 34 eval questions across all source types: every value from 0.30 to 0.65 separates answerable from unanswerable questions (`python -m app.evals --calibrate`, results in [`TECH.md`](TECH.md) §6). Re-check it on real usage.
