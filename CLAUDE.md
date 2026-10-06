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
- **No fake models.** Providers are real LangChain providers chosen in `.env` (`openai`, `google_genai`, `ollama` installed; others via `uv add langchain-<provider>`), built only through `init_chat_model`/`init_embeddings` in the factory. Tests run against local Ollama (`qwen2.5:7b`, `nomic-embed-text`); the integration test is skipped if Ollama is unavailable. Test fixtures live in `backend/tests/fixtures/`, never in `data/`, and stay small.
- Don't read `data/` content unless the user asks (`data/documents/docx/yield_improvement_report_q1.docx` was read to write `eval/golden.jsonl`; during the real-data run, Office properties and sheet headers were inspected to debug missing authors/dates).
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

This is the brief's context. **The actual dataset differs**: it centres on the Volta-7 automotive EV powertrain controller, customer NovaDrive Motors, and people such as Mike Chen, Lisa Park, Sara Nolan, James Ortiz and Anna Becker. All prompts are product-agnostic, and routing uses the people parsed from the data, not this table.

## Dataset (in `data/`, read-only)
- `data/meetings/`: 20 plain-text `.md` transcripts. Header lines: `Meeting:`, `Date: … Time: … Location: …`, `Attendees: Name (Role), …`, `Meeting Type:`. Then plain section labels (`Discussion`, `Decisions`, `Action Items`) and `Name: text` speaker turns.
- `data/documents/docx/` (5): corrective_action_8d, failure_analysis_htol, npi_checklist_volta7, pe_division_sop, yield_improvement_report_q1. Real OOXML; the author is in core properties, and body lines like `**Author:** Name, Role` / reviewers are also parsed. `npi_checklist_volta7.docx` carries python-docx's template timestamp, which the loader ignores (it is undated).
- `data/documents/pptx/` (5): real OOXML decks (the earlier plain-text `.pptx` and `_slides.md` copies were rebuilt/removed); author from core properties, one section per slide plus speaker notes. The loader's text fallback still handles non-OOXML files with an Office extension.
- `data/documents/xlsx/` (5): action_item_tracker, defect_pareto_log, reliability_test_matrix, test_time_breakdown, yield_tracker. They had no core properties; author, title and date were added (user-approved data change, sheet contents unchanged). If a sheet has no date property, the loader uses the latest row date.

## Tech stack
- Backend: Python 3.12, **uv**, FastAPI, LangChain (splitters, chains, structured output), **docling** (document parsing), **ChromaDB** (vectors), **rank-bm25** (lexical), **SQLite** (structured business data).
- Models (per component, via `.env`, any LangChain provider): `openai` (`gpt-4o-mini`, `text-embedding-3-small`), `google_genai` (`gemini-3.1-flash-lite`, `gemini-embedding-001`) or `ollama` (`qwen2.5:7b`, `nomic-embed-text`).
- Frontend: React 19 + Vite + TypeScript + Tailwind v4 (+ typography), react-router, react-markdown, recharts, lucide-react. The dev server proxies `/api` → `http://127.0.0.1:8000`.

## Commands
```bash
./dev.sh                                  # backend :8000 + frontend :5173 together
```
Backend (from `backend/`):
```bash
uv sync && cp .env.example .env           # pick providers (+ OPENAI_API_KEY for openai)
uv run uvicorn app.main:app --reload      # API on :8000, docs at /docs
uv run python -m app.ingestion            # ingest data/ (idempotent; --force, --dry-run = parse+chunk only)
uv run pytest                             # unit + Ollama end-to-end test
uv run pytest -m "not integration"        # fast unit tests only
uv run pytest tests/test_x.py::test_name  # single test
uv run ruff check . && uv run ruff format .
uv run python -m app.evals --dataset golden   # offline eval (--synthesize N first to generate a synthetic set)
./scripts/smoke_ex1.sh && ./scripts/smoke_ex2.sh   # curl smoke tests against a running server
```
Frontend (from `frontend/`): `npm install && npm run dev` (:5173), `npm run build` (type-check + build).

## Architecture
```
data/meetings/*.md      → loaders/meeting.py (deterministic title/date/attendees+roles/type/location)
data/documents/**/*.ext → loaders/office.py  (docling per slide/sheet; authors/reviewers/title from core
                                               props or body bylines; text fallback for non-OOXML)
  → docling_md.py (meetings: promote section labels to ##, keep speaker turns)
  → enrich.py (LLM structured output, cached by content hash + model + PROMPT_VERSION)
  → business_rules.apply_ingest_rules (R1-R3)
  → chunking.py (headings → merge small → recursive split of oversized; tables split by rows w/ header)
  → Chroma (scalar chunk metadata) + SQLite documents/action_items (+ normalized content for the viewer)

POST /api/chat/stream (SSE) | POST /api/query → answer/chat.py run_chat():
  guardrails.classify_input (injection heuristics + LLM: knowledge|small_talk|off_topic|prompt_injection)
  → condense follow-up with history → hybrid.retrieve (pre-filter → semantic + BM25 → RRF → pointwise
    LLM rerank) → stream tokens through StreamRedactor (PII) → citations.build_claims (re-attach,
    validate, drop uncited) → confidence.score_confidence → routing.suggest_routing if not confident
  → persist message (+routing, low_confidence gap) → metrics.record → final event
Feedback: feedback/actions.py (correct / reject→routing / thumbs) → gaps → review queue
Evals: evals/runner.py over eval/golden.jsonl + eval/synthetic.jsonl (LLM-generated from chunks)
```
- **Pointwise reranking is deliberate:** listwise prompts misaligned scores on qwen2.5:7b. The judge returns `{reason, relevance}`; the reason field improves small-model scoring.
- **The answer streams raw tokens, but the `final` event carries the validated answer.** The UI replaces the streamed text with it.
- **Every answered query is an assistant `messages` row:** message id = query id, used by `/api/query/{id}/…`.
- **Re-ingest is idempotent** (source path + content_hash + collection); deleted files are pruned. Bump `PROMPT_VERSION` in `enrich.py` when the enrichment prompt changes, then ingest with `--force`.
- **Chroma collections are per embedding model**, so switching models needs a re-ingest. Chroma metadata must be scalar, so lists are comma-joined there; canonical lists live in SQLite.
- **`init_db()` adds new columns to existing databases** (`_ADDED_COLUMNS` in `db/sqlite.py`) when the schema grows.

## Configuration (`.env`, see `backend/.env.example`)
Models, docling, chunk token budgets, retrieval/RRF/rerank, `CONFIDENCE_THRESHOLD`, `MIN_RETRIEVAL_SCORE`, `HISTORY_MESSAGES`, `GUARDRAILS_LLM`, `ROUTING_MAX_PEOPLE`, `ALERT_*` thresholds, storage paths, `CORS_ORIGINS`. Relative paths resolve from `backend/`. Restart the server after editing `.env`.

## Enrichment schema (`app/models/enrichment.py`)
`topic_domain` (yield | design | test_engineering | npi_program | supply_chain | customer | quality_compliance | executive_strategy | other), `priority` (critical | high | medium | low | none), `products`, `summary`, `key_topics`, `decisions`, `action_items[{owner, task, due_date}]`.

## SQLite tables (`app/db/schema.sql`)
`documents`, `action_items`, `enrichment_cache`, `conversations`, `messages` (assistant rows hold `payload_json` = the final answer payload, plus status and feedback), `routing_suggestions`, `gaps` (low_confidence | rejected | correction; review_status pending | reviewed | resolved), `metrics` (one row per answer), `eval_runs`, `eval_results`.

## API
| Method | Path | Purpose |
|---|---|---|
| GET | /api/health, /api/stats | health; counts by type, providers, threshold |
| POST | /api/ingest | ingest `data/` (`{"force": true}` to re-enrich) |
| GET | /api/documents[/{id}], /{id}/content, /{id}/file | metadata (filters); content + chunks for the viewer; original file |
| POST | /api/chat/stream | SSE: conversation, status, guardrail, sources, token*, final \| error |
| GET/PATCH/DELETE | /api/conversations[/{id}] | chat history |
| POST | /api/query | single-shot answer (same payload as `final`); `generate_answer:false` = retrieval only |
| GET | /api/query/{id} | stored answer |
| POST | /api/query/{id}/correct, /reject, /feedback | correction gap; rejection gap + routing; thumbs |
| POST | /api/routing/{id}/send, /dismiss | log the (edited) question as sent; dismiss |
| GET | /api/gaps[/{id}] | gaps & corrections (?type, ?status) |
| GET/PATCH | /api/review-queue[/{id}] | counts + items; review with note |
| GET | /api/metrics?window=24h\|7d\|30d | rollups vs previous window, timeseries, alerts |
| GET/POST | /api/evals, /api/evals/run, /api/evals/{id}, /api/evals/synthesize | eval runs |

Answer payload: `query_id, conversation_id, query, standalone_query, answer, claims[{text,citations,kind,supported}], dropped_claims, citations[{n, chunk_id, doc_id, source_file, source_type, title, section, date, attendees, authors, people, people_label, topic_domain, priority, products, snippet, scores}], cited, documents[DocumentMetadata], confidence, confidence_detail, confident, status (answered|routed|refused|blocked|rejected|corrected), routing[], guardrails, retrieval, latency_ms, first_token_ms`.

## Folder layout
```
backend/app/{config.py, main.py, state.py, llm/, db/, models/, ingestion/, retrieval/, answer/,
             routing/, feedback/, observability/, evals/, api/}
backend/{eval/golden.jsonl, scripts/, tests/}
frontend/src/{api/client.ts, types.ts, lib/, components/{ui,meta,citations,chat,charts}.tsx, pages/}
docs/MEASUREMENT.md, dev.sh
```
Frontend charts use the validated palette tokens `--series-1..3` in `index.css`. Single-series charts use slot 1; never use dual axes.

## Open decisions (also see TASKS.md)
- The confidence threshold (0.55) is a heuristic. Calibrate it with the golden eval on the real data.
- Legacy `.doc/.ppt/.xls` go through LibreOffice if it's installed; otherwise they fail with a clear error in the report.
- No auth: `submitted_by`, the reviewer and `sent_by` are free text (the user name lives in localStorage).
