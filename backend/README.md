# FastChip Knowledge API (backend)

FastAPI service that ingests meeting transcripts from `data/meetings/`, derives structured metadata, stores it in **SQLite** + **ChromaDB**, and answers natural-language queries with hybrid retrieval (semantic + BM25 → RRF → LLM rerank).

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
| `DATA_DIR` | `../data` | Source data; meetings are read from `DATA_DIR/meetings` |
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

## 4. Ingestion (load → enrich → chunk → embed → store)

### Trigger through the API

```bash
curl -X POST localhost:8000/api/ingest
```

Force re-processing of every file (re-enrich + re-embed):

```bash
curl -X POST localhost:8000/api/ingest \
  -H 'content-type: application/json' -d '{"force": true}'
```

### Trigger from the command line (no server needed)

```bash
uv run python -m app.ingestion            # ingest
uv run python -m app.ingestion --force    # re-process everything
uv run python -m app.ingestion --dry-run  # parse + chunk only, no model calls (inspect parsing)
```

### Response

```json
{
  "collection": "fastchip__ollama-nomic-embed-text",
  "files_found": 20,
  "ingested": 20,
  "skipped_unchanged": 0,
  "removed": 0,
  "chunks_written": 61,
  "duration_s": 74.2,
  "ingested_files": ["meetings/..."],
  "failed": [],
  "warnings": []
}
```

- **Idempotent:** a file is skipped if its content and the active collection are unchanged.
- **Pruning:** files deleted from `data/meetings` are removed from Chroma and SQLite.
- **Failures** are reported per file and don't stop the run.
- **`warnings`** list files where no attendee list was found.
- A second ingest started while one is running returns **409**.

### What happens per file

| Step | Code |
|---|---|
| Parse title, date, attendees (+roles), meeting type, location; no LLM involved | `app/ingestion/loaders/meeting.py` |
| Promote section labels to headings, keep speaker turns, docling → markdown | `app/ingestion/docling_md.py` |
| LLM enrichment: topic_domain, priority, products, summary, key_topics, decisions, action_items (cached) | `app/ingestion/enrich.py` |
| Structure-aware recursive chunking | `app/ingestion/chunking.py` |
| Embed + store chunks in ChromaDB | `app/retrieval/vectorstore.py` |
| Store document metadata + action items in SQLite | `app/db/repository.py` |
| Orchestration | `app/ingestion/pipeline.py` |

**Chunking strategy:**
1. Split on markdown headings so chunks never cross sections.
2. Merge sections smaller than `CHUNK_MIN_TOKENS`.
3. Split only sections larger than `CHUNK_MAX_TOKENS`, recursively by paragraph/speaker turn, then line, sentence, clause and word.

Each chunk starts with a context line (`[title | date | section]`).

---

## 5. Query

### Trigger

```bash
curl -s -X POST localhost:8000/api/query \
  -H 'content-type: application/json' \
  -d '{"query": "What caused the low first-silicon yield and who owns the fix?"}' | jq
```

### Request fields

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | string | (required) | Natural-language question |
| `filters.topic_domain` | string | — | e.g. `yield`, `design`, `test_engineering`, `npi_program`, `supply_chain`, `customer`, `quality_compliance`, `executive_strategy`, `other` |
| `filters.priority` | string | — | `critical`, `high`, `medium`, `low`, `none` |
| `filters.source_type` | string | — | `meeting` |
| `filters.person` | string | — | Attendee name, case-insensitive substring |
| `filters.date_from` / `filters.date_to` | ISO date | — | Inclusive date range |
| `top_k` | int 1–20 | `TOP_K` | Number of results |
| `rerank` | bool | `true` | Apply LLM reranking |
| `generate_answer` | bool | `true` | Generate an answer with `[n]` citations |

Example with filters:

```bash
curl -s -X POST localhost:8000/api/query -H 'content-type: application/json' -d '{
  "query": "open action items",
  "filters": {"topic_domain": "yield", "person": "Lisa", "date_from": "2024-01-01"},
  "top_k": 5
}' | jq
```

### Response

```json
{
  "query": "...",
  "answer": "First-silicon yield was 41.2% ... [1][2]",
  "results": [
    {
      "rank": 1,
      "chunk_id": "a1b2...:003",
      "doc_id": "a1b2...",
      "text": "[Meeting title | 2024-01-15 | Discussion]\n...",
      "section": "Discussion",
      "source_file": "meetings/meeting_....md",
      "source_type": "meeting",
      "title": "...",
      "date": "2024-01-15",
      "attendees": ["..."],
      "topic_domain": "yield",
      "priority": "high",
      "products": ["..."],
      "scores": {"semantic": 0.71, "semantic_rank": 1, "bm25": 4.2, "bm25_rank": 2,
                 "fused": 0.032, "rerank": 9.0}
    }
  ],
  "documents": [
    {"doc_id": "...", "source_file": "...", "title": "...", "date": "...",
     "attendees": ["..."], "attendee_roles": {"Name": "Role"}, "meeting_type": "...",
     "location": "...", "topic_domain": "...", "priority": "...", "products": ["..."],
     "key_topics": ["..."], "summary": "...", "decisions": ["..."],
     "action_items": [{"owner": "...", "task": "...", "due_date": "..."}], "n_chunks": 3,
     "ingested_at": "..."}
  ],
  "retrieval": {"semantic_candidates": 20, "bm25_candidates": 14, "fused_candidates": 20,
                "reranker": "llm", "latency_ms": 1850}
}
```

- `[n]` in `answer` refers to `results[n-1]`.
- `documents` holds the derived metadata for every meeting that appears in `results`.

### How retrieval works (`app/retrieval/`)

1. **Semantic:** ChromaDB cosine similarity (`vectorstore.py`).
2. **Lexical:** BM25 over all chunks, kept in memory and rebuilt after ingestion (`bm25.py`).
3. **Fusion:** weighted Reciprocal Rank Fusion (`hybrid.py`).
4. **Rerank:** the LLM rates each candidate from 0 to 10, one call per passage, run concurrently (`rerank.py`).
5. **Answer:** grounded generation with `[n]` citations (`app/answer/generate.py`).

The topic/priority/source_type filters are pushed into Chroma; the person and date filters are applied to both retrievers.

---

## 6. All endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness: `{"status":"ok"}` |
| GET | `/api/stats` | Document/chunk counts, active collection, LLM/embedding/reranker, data dir |
| POST | `/api/ingest` | Run ingestion (body optional: `{"force": true}`) |
| POST | `/api/query` | Natural-language query (see section 5) |
| GET | `/api/documents` | All ingested documents with derived metadata. Query params: `topic_domain`, `priority`, `source_type`, `person` |
| GET | `/api/documents/{doc_id}` | One document's metadata (404 if unknown) |

```bash
curl -s localhost:8000/api/stats | jq
curl -s 'localhost:8000/api/documents?topic_domain=yield&person=lisa' | jq
curl -s localhost:8000/api/documents/<doc_id> | jq
```

---

## 7. Storage

| Store | Location | Contents |
|---|---|---|
| SQLite | `storage/app.db` | `documents` (metadata + enrichment), `action_items`, `enrichment_cache` |
| ChromaDB | `storage/chroma/` | Chunk vectors + chunk metadata, one collection per embedding model |

Inspect SQLite:

```bash
sqlite3 storage/app.db "select source_file, topic_domain, priority, n_chunks from documents"
```

**Full reset:** stop the server, `rm -rf storage/app.db* storage/chroma`, then ingest again.

---

## 8. Tests

```bash
uv run pytest                        # unit tests + end-to-end test against local Ollama
uv run pytest -m "not integration"   # fast unit tests only
uv run pytest tests/test_chunking.py::test_small_section_kept_whole_with_metadata  # one test
./scripts/smoke_ex1.sh               # curl smoke test against a running server
uv run ruff check . && uv run ruff format .
```

The integration test uses `tests/fixtures/` (never `data/`) and needs Ollama with `qwen2.5:7b` and `nomic-embed-text`. It's skipped automatically if those aren't available.

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
| Slow queries with Ollama | Local reranking takes ~15–20s; set `RERANKER=none` or use OpenAI |
| `files_found: 0` | Check that `DATA_DIR` points to the folder containing `meetings/` |
