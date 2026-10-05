# FastChip Knowledge API (backend)

FastAPI service that ingests meeting transcripts (`data/meetings/`) and Office documents (`data/documents/`) and derives structured metadata, stored in **SQLite** + **ChromaDB**. It answers natural-language questions with hybrid retrieval (semantic + BM25 → RRF → LLM rerank), guardrails, validated citations, confidence scoring and routing. It also captures gaps and corrections, records quality metrics and runs evals.

---

## 1. Setup

```bash
cd backend
uv sync                      # install dependencies (Python 3.12)
cp .env.example .env         # then edit .env (see section 2)
```

---

## 2. Configuration: OpenAI or Ollama

**All configuration goes in `backend/.env`.** You never edit code to switch models.

`app/config.py` only declares which settings exist, their types and fallback defaults. Values resolve in this order, first match wins:

1. Real environment variable (`LLM_PROVIDER=ollama uv run uvicorn ...`)
2. `backend/.env`
3. Default in `app/config.py`

The **LLM** and the **embedding model** are chosen independently.

### Option A: OpenAI

```env
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
```

### Option B: local Ollama (no API key)

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
ollama serve                 # or run the Ollama desktop app
```

```env
OLLAMA_BASE_URL=http://localhost:11434
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:7b
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
```

### Mixing providers

For example, local embeddings with an OpenAI LLM:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
```

### What each model is used for

| Component | Setting | Used for |
|---|---|---|
| LLM | `LLM_PROVIDER`, `LLM_MODEL` | Metadata enrichment at ingest, reranking and answer generation at query time |
| Embeddings | `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL` | Embedding chunks at ingest and the query at search time |

### Important

- **Restart the server after editing `.env`.** Settings are cached, and `--reload` only watches `.py` files.
- **Changing the embedding model requires re-ingesting.** Each embedding model gets its own Chroma collection (e.g. `fastchip__ollama-nomic-embed-text`), so vectors from different models never mix. Run `POST /api/ingest` after switching.
- **Changing the LLM** doesn't require re-ingesting. To re-derive metadata with the new LLM, ingest with `{"force": true}`.
- `GET /api/stats` shows the active providers and collection.
- With `*_PROVIDER=openai` and no `OPENAI_API_KEY`, calls return **HTTP 503** with a clear message.

### All settings (`.env`)

| Setting | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | (empty) | Required when any provider is `openai` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `LLM_PROVIDER` / `LLM_MODEL` | `openai` / `gpt-4o-mini` | LLM (`openai` or `ollama`) |
| `LLM_TEMPERATURE` | `0` | LLM temperature |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | `openai` / `text-embedding-3-small` | Embeddings (`openai` or `ollama`) |
| `USE_DOCLING` | `true` | Parse documents with docling |
| `CHUNK_MAX_TOKENS` | `512` | Upper bound per chunk; sections under this stay whole |
| `CHUNK_MIN_TOKENS` | `80` | Smaller sections merge with a neighbour |
| `CHUNK_OVERLAP_TOKENS` | `64` | Overlap, used only when an oversized section is split |
| `ENRICH_MAX_CHARS` | `12000` | Max characters sent to the LLM for enrichment |
| `TOP_K` | `6` | Results returned per query |
| `CANDIDATE_K` | `20` | Candidates taken from each retriever before fusion |
| `SEMANTIC_WEIGHT` / `BM25_WEIGHT` | `1.0` / `1.0` | Weights in reciprocal rank fusion |
| `RRF_K` | `60` | RRF constant |
| `RERANKER` | `llm` | `llm` (LLM relevance judge) or `none` |
| `RERANK_TOP_N` | `10` | Fused candidates sent to the reranker |
| `RERANK_CONCURRENCY` | `4` | Parallel rerank calls |
| `RERANK_MAX_CHARS` | `1200` | Passage length sent to the reranker |
| `CONFIDENCE_THRESHOLD` | `0.55` | Below this an answer is low confidence → routing + gap |
| `MIN_RETRIEVAL_SCORE` | `0.25` | A weak top semantic match caps confidence |
| `HISTORY_MESSAGES` | `6` | Chat messages used to rewrite follow-up questions |
| `GUARDRAILS_LLM` | `true` | LLM input classifier (injection heuristics always run) |
| `ROUTING_MAX_PEOPLE` | `3` | Routing suggestions per answer |
| `ALERT_*` | see `.env.example` | Monitoring thresholds (answer rate, confidence, citation validity, negative feedback, p95 latency, baseline drop, min samples) |
| `DATA_DIR` | `../data` | Source data: `DATA_DIR/meetings` and `DATA_DIR/documents` |
| `CHROMA_DIR` | `./storage/chroma` | ChromaDB persistence |
| `CHROMA_COLLECTION` | `fastchip` | Collection prefix (the embedding model is appended) |
| `SQLITE_PATH` | `./storage/app.db` | SQLite database |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |

Relative paths resolve from `backend/`.

---

## 3. Run the server

```bash
uv run uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Interactive docs (Swagger): http://localhost:8000/docs

---

## 4. Ingestion (load → enrich → rules → chunk → embed → store)

Sources: `data/meetings/*.md` and `data/documents/**/*.{docx,pptx,xlsx,doc,ppt,xls}`.

```bash
curl -X POST localhost:8000/api/ingest                                   # new / changed files
curl -X POST localhost:8000/api/ingest -H 'content-type: application/json' -d '{"force": true}'
uv run python -m app.ingestion [--force] [--dry-run]                     # CLI; dry-run = parse + chunk, no models
```
You can also click **Ingest** on the app's Documents page.

The report includes `files_found`, `ingested`, `skipped_unchanged`, `removed`, `chunks_written`, `by_type`, `failed[]` and `warnings[]`. Warnings flag Office files that aren't real OOXML (parsed as text) and files with no attendees or authors. The server log prints one `[i/N] file: n chunks (s)` line per file.

| Step | Code |
|---|---|
| Meetings: title, date, attendees + roles, meeting type, location (deterministic, no LLM) | `app/ingestion/loaders/meeting.py` |
| Office: docling content per slide (`## Slide N` + speaker notes) / sheet (`## Sheet: name`); author, reviewers, title and date from core properties or body bylines (`**Author:** Name, Role`); non-OOXML → text fallback; legacy formats via LibreOffice | `app/ingestion/loaders/office.py` |
| LLM enrichment (topic, priority, products, summary, key topics, decisions, action items), cached | `app/ingestion/enrich.py` |
| Business rules R1-R3 (priority floor, owners and products must appear in the source) | `app/answer/business_rules.py` |
| Structure-aware recursive chunking; tables split by rows with the header repeated | `app/ingestion/chunking.py` |
| Embed + store in Chroma; metadata + content in SQLite | `app/retrieval/vectorstore.py`, `app/db/repository.py` |

Ingestion is idempotent per content hash and active collection, and deleted files are pruned.

---

## 5. Asking questions

### Streaming chat (used by the web app)
```bash
curl -N -X POST localhost:8000/api/chat/stream -H 'content-type: application/json' \
  -d '{"message": "What caused the low first-silicon yield?", "conversation_id": null}'
```
Server-Sent Events, in order:

| Event | Data |
|---|---|
| `conversation` | `{conversation_id, title}` (pass `conversation_id` back for follow-ups) |
| `status` | `{stage: guardrails \| retrieving \| generating \| routing, query?}` |
| `guardrail` | `{category: knowledge_question \| small_talk \| off_topic \| prompt_injection, reason, method}` |
| `sources` | `{citations[], documents[]}`, sent before any tokens |
| `token` | `{text}`, streamed and PII-redacted |
| `final` | the validated answer payload (below); replaces the streamed text |
| `error` | `{detail}` |

### Single-shot
```bash
curl -s -X POST localhost:8000/api/query -H 'content-type: application/json' \
  -d '{"query": "Who owns the HTOL failure analysis?", "filters": {"source_type": "docx"}}' | jq
```
Body fields:
- `query`
- `filters`: `topic_domain`, `priority`, `source_type` (meeting | docx | pptx | xlsx), `person`, `date_from`, `date_to`
- `top_k`, `rerank`
- `generate_answer`: `false` returns retrieval only

All filters are pre-filters, applied before ranking.

### Answer payload (`final` event / `/api/query`)
```json
{
  "query_id": "…", "conversation_id": "…", "query": "…", "standalone_query": "…",
  "answer": "First-silicon yield was 41.2% [1] …",
  "claims": [{"text": "…", "citations": [1], "kind": "fact", "supported": true}],
  "dropped_claims": ["uncited statement removed by rule R5"],
  "citations": [{"n": 1, "chunk_id": "…", "doc_id": "…", "source_file": "documents/docx/….docx",
                 "source_type": "docx", "title": "…", "section": "…", "date": "2024-03-31",
                 "people": ["James Ortiz"], "people_label": "Author", "attendees": [], "authors": ["James Ortiz"],
                 "topic_domain": "yield", "priority": "high", "products": ["Volta-7"],
                 "snippet": "…", "scores": {"semantic": 0.71, "bm25": 4.2, "fused": 0.03, "rerank": 9}}],
  "cited": [1], "documents": [{"…": "derived metadata per source document"}],
  "confidence": 0.78, "confident": true,
  "status": "answered | routed | refused | blocked",
  "routing": [{"routing_id": "…", "person": "…", "role": "…", "reason": "…", "matched_sources": [], "draft_question": "…"}],
  "guardrails": {"category": "knowledge_question", "pii_redactions": 0, "uncited_dropped": 1},
  "latency_ms": 2100, "first_token_ms": 900
}
```

### Pipeline (`app/answer/chat.py`)
1. **Input guardrails:** prompt-injection heuristics plus an LLM classifier. Injection is blocked, off-topic is declined, small talk gets a canned reply.
2. **Condense:** a follow-up is rewritten into a standalone query using the conversation history.
3. **Retrieve:** pre-filter → semantic + BM25 → weighted RRF → pointwise LLM rerank.
4. **Generate:** the answer is streamed with `[n]` citations; excerpts are treated as untrusted data; the newest source wins on conflict (R6).
5. **Validate:** misplaced citations are re-attached, invalid ones removed and uncited factual claims dropped (R5). PII is redacted.
6. **Confidence:** computed from retrieval, rerank and citation coverage. Below `CONFIDENCE_THRESHOLD`, routing suggestions are added and a `low_confidence` gap is created.
7. **Persist:** the message, routing, gap and a metrics row are stored.

---

## 6. All endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health`, `/api/stats` | Liveness; counts by type, providers, collection, threshold |
| POST | `/api/ingest` | Run ingestion (`{"force": true}` optional) |
| GET | `/api/documents` | Documents with derived metadata (`topic_domain`, `priority`, `source_type`, `person`) |
| GET | `/api/documents/{id}`, `/content`, `/file` | Metadata; normalized content + chunks (viewer); original file download |
| POST | `/api/chat/stream` | Streaming conversational answer (SSE) |
| GET/PATCH/DELETE | `/api/conversations[/{id}]` | List, read (with messages), rename, delete conversations |
| POST | `/api/query` | Single-shot answer |
| GET | `/api/query/{id}` | Stored answer with current status, feedback and routing |
| POST | `/api/query/{id}/correct` | `{correction, submitted_by}` → correction gap (keeps the original query + answer) |
| POST | `/api/query/{id}/reject` | `{reason, submitted_by}` → rejected gap + routing suggestions |
| POST | `/api/query/{id}/feedback` | `{rating: "up" \| "down" \| null}` |
| POST | `/api/routing/{id}/send` | `{question, sent_by}` → marks the (edited) question sent (log only, no delivery) |
| POST | `/api/routing/{id}/dismiss` | Dismiss a suggestion |
| GET | `/api/gaps`, `/api/gaps/{id}` | Gaps and corrections (`?type=low_confidence\|rejected\|correction&status=…`) |
| GET | `/api/review-queue` | `{counts, items}`, pending first |
| PATCH | `/api/review-queue/{id}` | `{review_status: pending\|reviewed\|resolved, reviewer_note}` |
| GET | `/api/metrics?window=24h\|7d\|30d` | Current vs previous window, timeseries, alerts |
| GET | `/api/evals` | Datasets and runs |
| POST | `/api/evals/run` | `{dataset: golden\|synthetic\|all}` → background run (202) |
| GET | `/api/evals/{id}` | Run summary + per-case results |
| POST | `/api/evals/synthesize` | `{n}` → LLM-generated synthetic set from ingested chunks |

---

## 7. Storage

| Store | Location | Contents |
|---|---|---|
| SQLite | `storage/app.db` | `documents`, `action_items`, `enrichment_cache`, `conversations`, `messages`, `routing_suggestions`, `gaps`, `metrics`, `eval_runs`, `eval_results` |
| ChromaDB | `storage/chroma/` | Chunk vectors + chunk metadata, one collection per embedding model |
| Eval sets | `eval/golden.jsonl`, `eval/synthetic.jsonl` | Questions with expected sources and keywords |

To reset everything, stop the server, run `rm -rf storage/app.db* storage/chroma`, then ingest again.

---

## 8. Tests and evals

```bash
uv run pytest                        # unit tests + end-to-end against local Ollama
uv run pytest -m "not integration"   # fast unit tests only
./scripts/smoke_ex1.sh               # Ex1 curl checks against a running server
./scripts/smoke_ex2.sh               # Ex2: both sources, traceability, guardrails, routing, gaps, review, metrics
uv run python -m app.evals --dataset golden            # exits 1 if below target
uv run python -m app.evals --synthesize 20 --dataset synthetic
```
The integration test uses `tests/fixtures/` plus small real Office files it generates (never `data/`). It needs Ollama with `qwen2.5:7b` and `nomic-embed-text` and is skipped automatically otherwise.

Eval metrics:
- **Retrieval:** hit rate (an expected source was retrieved), MRR, cited-expected (the answer cites an expected source).
- **Answerability accuracy:** confident on answerable questions, abstains or routes on unanswerable ones.
- **Keyword recall.**
- **LLM judge:** faithfulness and relevance.
- **Citation validity.**

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `503 OPENAI_API_KEY is not set` | Add the key to `.env`, or switch the providers to `ollama`; restart the server |
| `503 Model provider unreachable` | Start Ollama (`ollama serve`) and check `OLLAMA_BASE_URL` |
| `.env` change has no effect | Restart the server (settings are cached) |
| Query returns no results | Run `POST /api/ingest`; check that `GET /api/stats` shows `chunks > 0` for the active collection |
| Results empty after switching embedding model | Expected: the new model has its own collection, so re-ingest |
| `409` on ingest | An ingestion run is already in progress |
| Slow answers with Ollama | Local qwen2.5:7b runs guard + rewrite + rerank + generation sequentially (~20–60s). Set `RERANKER=none`, `GUARDRAILS_LLM=false`, or use OpenAI |
| A `.pptx` shows `format: text-fallback` | The file isn't real PowerPoint (plain text with a .pptx name); it's still ingested and cited under its own name |
| `files_found: 0` | Check that `DATA_DIR` points to the folder containing `meetings/` |
