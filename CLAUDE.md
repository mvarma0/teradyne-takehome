# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is
A take-home assignment: a RAG knowledge system for the fictional **FastChip Semiconductor**, built in three exercises.
- **Ex1:** ingest meeting transcripts, derive structured metadata, store it in queryable form, and expose a natural-language query API.
- **Ex2:** add Office docs (.docx/.pptx/.xlsx, plus legacy .doc/.ppt/.xls) to the same API. Every surfaced fact traces back to source file + author/attendees. Low-confidence answers produce routing (who to ask, why, draft question). Corrections and rejections are captured as gaps that can be retrieved through the API. Instrumentation catches quality degradation.
- **Ex3:** a React web app with an answer that has per-claim citations (file + author), metadata badges, an editable routing panel and a team-lead review queue. Also `docs/MEASUREMENT.md`: one 30-day metric, one paragraph.

The original brief is in `take-home-assignment.md`. **`TASKS.md` is the execution plan.** Work tasks in order. A task is done only after its Verify step passes. Then change `- [ ]` to `- [x]`.

## Hard rules
- **Never create, modify or delete anything under `data/`.** It's the user-provided corpus and is read-only.
- **People fields (attendees, authors) come only from source parsing, never from the LLM.** The LLM derives topic, priority, products, summary, decisions and action items.
- **Every claim in an answer must cite a retrieved chunk.** Claims with invalid citations are dropped, not shown.
- **Nothing constructs LLM or embedding clients directly.** Always use `app/llm/factory.py` (`get_llm()`, `get_embeddings()`). All tunables live in `app/config.py` (pydantic-settings, `.env`).
- Tests must run offline. In `APP_ENV=test` the factory returns `FakeListChatModel` / `DeterministicFakeEmbedding`. Test fixtures are generated under `backend/tests/`, never in `data/`.
- Business rules live in one place, `app/answer/business_rules.py`, and are applied identically to all source types.

## Company context (FastChip Semiconductor, all fictional)
- About 500 employees. HQ in Austin, TX; design center in Portland, OR; test facility in Penang, Malaysia.
- Products: automotive-grade MCUs and power-management ICs.
- Current situation: ramping production of the **Falcon-7** next-gen automotive MCU while managing yield issues on the existing **Eagle-5** line.
- Challenges: yield optimization, AEC-Q100 automotive qualification, customer deadlines, supply chain coordination.

| Dept | People |
|---|---|
| Engineering | Sarah Chen (VP), Marcus Rivera (Sr. Process Engineer), Priya Patel (Design Lead), James Kim (Test Engineer) |
| Operations | David Park (VP Ops), Lisa Wong (Supply Chain Manager), Tom Bradley (Fab Manager) |
| Product/Business | Rachel Adams (Product Manager), Mike O'Brien (Sales Director), Jennifer Liu (Quality Manager) |
| Leadership | Robert Zhang (CEO), Amanda Foster (CTO), Kevin Nash (CFO) |

This table is the routing people directory (`app/routing/people.py`).

## Dataset (in `data/`, read-only)
- `data/meetings/`: 20 `.md` transcripts (attendees, date, free-form text with embedded decisions and action items)
  - 1-4: Eagle-5 yield · 5-8: Falcon-7 design reviews · 9-11: supply chain/vendors · 12-14: customer escalations · 15-17: quality & compliance · 18-20: executive strategy
- `data/documents/docx/` (5): Eagle-5 Yield Analysis Report, Falcon-7 Design Spec, Quarterly Quality Report, Vendor Evaluation Summary, Customer Escalation Procedures
- `data/documents/pptx/` (5): Falcon-7 Program Review, Eagle-5 Yield Improvement Plan, Q3 Business Review, Supply Chain Risk Assessment, AEC-Q100 Qualification Status
- `data/documents/xlsx/` (5): Eagle-5 Yield Data by Wafer Lot, Falcon-7 Timeline & Milestones, Vendor Scorecard Matrix, Customer Complaint Tracker, Test Coverage Matrix

Office authors come from core properties (`author`/`creator`), with a fallback to an "Author:/Owner:" line in the body, else `"unknown"`.

## Tech stack
- Backend: Python 3.12, **uv**, FastAPI, LangChain (loaders, splitters, chains, structured output), **ChromaDB** (vectors), **SQLite** (structured business data), OpenAI `gpt-4o-mini`, OpenAI `text-embedding-3-small` by default (HF sentence-transformers optional via `EMBEDDING_PROVIDER=huggingface`). Office parsing uses python-docx, python-pptx and openpyxl.
- Frontend: React + Vite + TypeScript + Tailwind. The dev server proxies `/api` → `http://localhost:8000`.

## Commands
Backend (run from `backend/`):
```bash
uv sync                                   # install
cp .env.example .env                      # then set OPENAI_API_KEY
uv run uvicorn app.main:app --reload      # API on :8000
uv run python -m app.ingestion            # ingest data/ (idempotent; --dry-run, --only meetings|documents)
uv run pytest                             # all tests (offline)
uv run pytest tests/test_x.py::test_name  # single test
uv run ruff check . && uv run ruff format .
uv run python -m eval.run_eval            # golden-set quality eval (needs API key + ingested data)
./scripts/smoke_ex1.sh / smoke_ex2.sh     # curl smoke tests against a running server
```
Frontend (run from `frontend/`):
```bash
npm install && npm run dev                # UI on :5173
npm run build                             # type-check + build
```

## Architecture
```
data/ → loaders (meeting/docx/pptx/xlsx/legacy) → SourceDoc(text, deterministic meta)
      → enrich.py (LLM structured output, cached by content hash) → SQLite documents/action_items
      → chunking.py → Chroma (flattened chunk metadata)
POST /api/query → retriever (similarity + metadata filters) → answer chain (claims[] with citation ids)
      → citations.py (validate) → confidence.py → business_rules.py
      → confident ? answer : routing/router.py (who/why/draft) → log queries + metrics
```
- Re-ingest is idempotent: documents are keyed by source path + content_hash, and their old chunks are deleted before upsert.
- The Chroma collection name gets the embedding model as a suffix, so switching models needs a re-ingest and never mixes vectors.
- Chroma metadata must be scalar, so lists (attendees, authors, products) are stored as comma-joined strings. Canonical lists live in SQLite.
- Confidence combines top/mean retrieval score, citation coverage and LLM self-rated answerability, thresholded by `CONFIDENCE_THRESHOLD`. A low-confidence result auto-creates a `low_confidence` gap and routing suggestions.

## Configuration (`.env`, see `backend/.env.example`)
`APP_ENV, OPENAI_API_KEY, LLM_PROVIDER, LLM_MODEL, LLM_TEMPERATURE, EMBEDDING_PROVIDER, EMBEDDING_MODEL, CHUNK_SIZE, CHUNK_OVERLAP, TOP_K, CONFIDENCE_THRESHOLD, MIN_RETRIEVAL_SCORE, DATA_DIR, CHROMA_DIR, CHROMA_COLLECTION, SQLITE_PATH, CORS_ORIGINS, ALERT_*` thresholds.

## Enrichment schema (`app/models/enrichment.py`)
- `topic_domain`: `yield | design | supply_chain | customer | quality_compliance | executive_strategy | other`
- `priority`: `critical | high | medium | low | none`
- `products`: list (e.g. Eagle-5, Falcon-7)
- `summary`: str
- `decisions`: list[str]
- `action_items`: list[{owner, task, due_date?}]

## SQLite tables (`app/db/schema.sql`)
- `documents`: id, source_file, source_type, title, date, authors_json, attendees_json, content_hash, topic_domain, priority, products_json, summary, decisions_json, enrichment_json, ingested_at
- `action_items`: id, document_id, owner, task, due_date
- `enrichment_cache`: content_hash, model, enrichment_json
- `queries`: id, query_text, filters_json, answer, claims_json, citations_json, confidence, status (answered|routed|rejected|corrected), latency_ms, created_at
- `routing_suggestions`: id, query_id, person, role, reason, matched_sources_json, draft_question, edited_question, status (suggested|sent|dismissed), sent_at
- `gaps`: id, query_id, type (low_confidence|rejected|correction), original_answer, correction_text, submitted_by, review_status (pending|reviewed|resolved), reviewer_note, created_at, reviewed_at
- `metrics`: id, query_id, top_score, mean_score, n_citations, citation_valid_ratio, confidence, latency_ms, tokens_in, tokens_out, created_at

## API
| Method | Path | Purpose |
|---|---|---|
| GET | /api/health | health |
| POST | /api/ingest | run the ingestion pipeline |
| GET | /api/documents | list docs with derived metadata (filters: topic_domain, priority, source_type, person) |
| POST | /api/query | NL query → answer, claims+citations, metadata, confidence, routing? |
| GET | /api/query/{id} | fetch a logged query |
| POST | /api/query/{id}/correct | capture a correction with the original query |
| POST | /api/query/{id}/reject | reject → gap + routing |
| POST | /api/routing/{id}/send | log the edited question as sent (no real delivery) |
| GET | /api/gaps, /api/gaps/{id} | gaps & corrections (?type, ?status) |
| GET/PATCH | /api/review-queue[/{id}] | team-lead queue; mark reviewed/resolved with a note |
| GET | /api/metrics | rolling 24h/7d quality metrics + alert flags |

Query response shape:
```json
{"query_id": "...", "answer": "...", "claims": [{"text": "...", "citations": [1]}],
 "citations": [{"n": 1, "source_file": "...", "source_type": "md|docx|pptx|xlsx", "location": "slide 3",
                "authors": [], "attendees": [], "date": "...", "snippet": "...", "score": 0.82}],
 "results_metadata": [{"source_file": "...", "topic_domain": "...", "priority": "...", "products": []}],
 "confidence": 0.71, "confident": true,
 "routing": [{"routing_id": "...", "person": "...", "role": "...", "reason": "...", "matched_sources": [], "draft_question": "..."}]}
```

## Folder layout
```
backend/app/{config.py, main.py, llm/, db/, models/, ingestion/{loaders/,enrich.py,chunking.py,pipeline.py}, retrieval/, answer/, routing/, feedback/, observability/, api/}
backend/{eval/, scripts/, tests/}
frontend/src/{api/, pages/, components/, types.ts}
docs/MEASUREMENT.md
```

## Open decisions (also see TASKS.md)
- Legacy `.doc/.ppt/.xls` are handled by a LibreOffice `soffice --convert-to` shim if it's installed, otherwise skipped with a warning (the dataset has none).
- No auth: `submitted_by` and the reviewer are free text.
- The confidence threshold gets calibrated against `eval/golden.jsonl`.
