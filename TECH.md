# Technical design

How the FastChip knowledge system works under the hood, and why each choice was made. For setup see [README.md](README.md); for how each requirement is met see [DELIVERABLE.md](DELIVERABLE.md).

---

## 1. Architecture at a glance

```
data/meetings/*.md ─┐
data/documents/**  ─┴─► loaders.py ─► ingest.py ───────────────────────────────┐
                        (parse, people,   (LLM enrichment → rules.py →           │
                         dates, title)     chunking → embed)                     ▼
                                                                  ChromaDB (vectors + chunk metadata)
                                                                  SQLite   (documents, action items,
                                                                            chat, routing, gaps, metrics,
                                                                            evals)
question ─► api.py ─► answer.py ─► guardrails.py ─► search.py ─► LLM answer ─► citation check
                                    (injection, topic,  (filters → semantic   (stream, PII     (re-attach,
                                     PII)                + BM25 → RRF →        redaction)       drop uncited)
                                                         LLM rerank)                              │
                                                                                                  ▼
                       feedback.py ◄── low confidence / reject ◄── confidence score ◄────────────┘
                       (who to ask, why, draft)        metrics.py (one row per answer → alerts)
```

The backend is one flat Python package, one module per concern:

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI app, startup (`init_db`), error handlers, `reset_all()` for cached singletons |
| `config.py` | Every setting, read from `backend/.env` (pydantic-settings) |
| `llm.py` | The only place model clients are built: `get_llm()`, `get_embeddings()`, `structured_llm()` |
| `schemas.py` | `SourceDoc`, `EnrichmentResult`, API request bodies, `RetrievedChunk` |
| `db.py` + `schema.sql` | SQLite connection, schema migration and all repositories |
| `loaders.py` | Meeting transcripts and Office files → `SourceDoc` (deterministic, no LLM) |
| `ingest.py` | Enrichment, chunking, the ingestion pipeline and its CLI |
| `rules.py` | Business rules R1–R3 (ingest) applied to every source type |
| `search.py` | Chroma, BM25, Reciprocal Rank Fusion, pointwise LLM rerank |
| `guardrails.py` | Prompt-injection rules, topic classifier, assistant-question rule, PII redaction |
| `answer.py` | The chat flow, citation validation (R5) and confidence |
| `feedback.py` | Routing suggestions and correct / reject / rate actions |
| `metrics.py` | Per-answer metrics, window rollups and alerts |
| `evals.py` | Golden and synthetic eval sets, LLM judge, CLI |
| `api.py` | Every HTTP route |

---

## 2. Ingestion

### 2.1 Parsing (`loaders.py`)
- **Meetings** are plain text with fixed header lines (`Meeting:`, `Date:`, `Attendees: Name (Role), …`, `Meeting Type:`). They are parsed with regular expressions, not an LLM, so **attendees and roles are copied exactly from the source**. Plain section labels (`Discussion`, `Decisions`, `Action Items`) are promoted to `##` headings so the chunker can split on them; speaker turns stay intact.
- **Office files** go through **docling**, which turns Word, PowerPoint and Excel into Markdown that keeps structure: headings, one `## Slide N` section per slide plus speaker notes, and one `## Sheet: name` section per sheet with a Markdown table. Authors, title and date come from the file's core properties, plus body bylines such as `Author: Name, Role` and reviewer lines. Known template timestamps are ignored, so an undated file stays undated. For a spreadsheet with no date property, the latest row date is used. Files that aren't real OOXML fall back to plain text; legacy `.doc/.ppt/.xls` are converted with LibreOffice when it is installed.
- **Why docling:** it preserves headings and tables, which the chunker needs. Text-only extractors flatten a slide deck or a sheet into one blob.

### 2.2 Enrichment (`ingest.py`)
One structured-output LLM call per document returns `topic_domain` (a fixed set of 9 values), `priority`, `products`, `summary`, `key_topics`, `decisions` and `action_items[{owner, task, due_date}]`.
- The prompt is product-agnostic and sees at most `ENRICH_MAX_CHARS` (12,000) characters.
- Results are **cached by content hash + model + prompt version** (`PROMPT_VERSION`), so re-ingesting unchanged files costs nothing, and switching the LLM or changing the prompt re-enriches automatically.
- **People are never taken from the LLM.** The model never writes attendees or authors.

### 2.3 Business rules (`rules.py`)
Applied identically to every source type, after enrichment:
- **R1, priority floor:** line-down, stop-ship, recall or safety language forces *critical*. Escalation, field returns, customer complaints, 8D, containment, a failed qualification or ISO 26262 forces at least *high*. The LLM's priority can only be raised, never lowered.
- **R2, owners must exist:** an action-item owner that does not appear in the source becomes "unassigned".
- **R3, products must exist:** products the LLM named that are not in the text are removed.
- **R4, people come only from parsing:** attendees and authors are set by the loaders. Enrichment has no people fields, so the LLM cannot invent one.

The rules applied are stored with the document and shown in the document viewer. R5 (uncited claims dropped) and R6 (newest source wins on conflict) apply at answer time (§4).

### 2.4 Chunking (`ingest.py`): structure-aware recursive
1. **Split on headings** (`#`, `##`, `###`) with LangChain's `MarkdownHeaderTextSplitter`. A chunk never straddles two sections, so each one covers a single meeting part, slide, sheet or report section.
2. **Merge small neighbours.** A section under `CHUNK_MIN_TOKENS` (80) merges with the next one, so a lone heading or a one-line slide does not become a weak chunk.
3. **Split only what is too big.** A section over `CHUNK_MAX_TOKENS` (512) is split recursively at the largest natural boundary that fits: paragraph or speaker turn → line → sentence → clause → word. Overlap (`CHUNK_OVERLAP_TOKENS`, 64) is used only in this case, so a fact cut at a boundary still appears whole in one chunk.
4. **Tables split by rows**, repeating the header row in every piece, so each piece of a spreadsheet stays self-describing ("Lot | Wafer | Yield%…").
5. **Context header.** Every chunk starts with `[title | date | section path]`. This helps both the embedding and BM25 ("HTOL" in the title finds the right report), and the answer model sees where each excerpt came from.

Token counts use tiktoken `cl100k_base`. Offline, a slightly conservative estimate is used instead, which is safe because budgets are upper bounds.

**Why 512 tokens as the maximum:**
- **It fits the content.** On this corpus there are 154 sections with a median of 188 tokens, and only 6 exceed 512. The cap almost never fires, so nearly every chunk is one whole section, which is the unit people cite.
- **It keeps retrieval precise.** One embedding vector per chunk averages its meaning. Past a few hundred tokens a chunk mixes topics (yield and test time and staffing), and similarity to a specific question drops. BM25 also favours shorter, focused passages.
- **It fits every embedding model.** `gemini-embedding-001` accepts 2,048 input tokens, `text-embedding-3-small` 8,191, and `nomic-embed-text` runs with a 2,048-token context in Ollama by default. 512 sits well inside all of them, so switching provider never truncates a chunk.
- **It keeps the answer prompt small.** Six excerpts of ≤512 tokens is about 3k tokens of context, cheap and fast on a local 7B model and well within its window.
- **It suits reranking and citations.** Each candidate is judged in its own LLM call, so shorter passages make reranking faster and more accurate, and a citation points at a passage short enough to read.

**Why 80 as the minimum:** fragments under about 80 tokens, such as a heading or a title slide, embed poorly and rank as noise. Merging them gives every chunk enough content to stand alone.

**Why overlap only on forced splits:** whole sections already end at natural boundaries. Overlapping them would only duplicate text and inflate BM25 counts.

**Result on this corpus:** 176 chunks from 40 files. The median is 239 tokens, 90% are under 486, and the largest is 537 (the 512 budget applies to the body; the context line is added after).

### 2.5 Storage and idempotency
- **Chroma** stores the vectors (cosine space) and scalar chunk metadata. Lists are comma-joined because Chroma metadata must be scalar.
- **SQLite** holds the canonical document metadata, action items and the normalized content used by the viewer.
- **There is one Chroma collection per embedding model** (`fastchip__<provider>-<model>`), so vectors from different models never mix. Switching the embedding model means re-ingesting into a fresh collection.
- **Re-ingest is idempotent.** A file is skipped when its content hash and target collection are unchanged, and documents whose files were deleted are pruned.

---

## 3. Retrieval (`search.py`)

```
filters ─► semantic top-20 (Chroma) ┐
        └► BM25 top-20 (rank-bm25)  ┴─► weighted RRF ─► top-10 ─► pointwise LLM rerank ─► top-6
```

- **Pre-filtering.** Topic, priority, source type, person and date range are resolved to a set of document ids in SQLite *before* ranking. Both retrievers search only those documents, so filtering never empties a top-k list after the fact.
- **Semantic + BM25.** Embeddings catch paraphrases ("why did yield drop"); BM25 catches exact identifiers that embeddings blur, such as `LOT-V7-005`, `FA-2026-0312`, `U162`, `Bin 7` or `CAR-2026-ND01`. The BM25 tokenizer also splits compound terms (`volta-7` → `volta`, `7`). The BM25 index is built in memory from the Chroma collection and rebuilt after each ingest.
- **Reciprocal Rank Fusion:** `score = Σ weight / (RRF_K + rank)` with `RRF_K = 60`. RRF fuses by rank, not raw score, so cosine similarities (0–1) and BM25 scores (unbounded) never need calibrating against each other. 60 is the standard constant: it flattens the gap between ranks 1 and 2 and still rewards documents that both retrievers find.
- **Pointwise LLM rerank.** The top `RERANK_TOP_N` (10) fused candidates are each scored 0–10 in **their own** structured-output call, run in parallel. The judge returns `{reason, relevance}`; asking for the reason first measurably improves small-model scoring. A listwise prompt (rank all 10 at once) was tried and misaligned scores and passages on `qwen2.5:7b`, so pointwise is deliberate. `RERANKER=none` skips this step for speed.
- **Why `TOP_K = 6`:** enough to cover a question that spans a meeting, its report and a tracker row, while keeping the prompt short and every citation number meaningful.

---

## 4. Answering (`answer.py`, `guardrails.py`)

**Input guardrails**, in order:
1. Prompt-injection regexes ("ignore previous instructions", "reveal your prompt", role-play tricks). A match blocks the message.
2. A fixed rule for questions about the assistant itself ("what is this system?", "what can you do?"), which get the built-in introduction.
3. An LLM classifier: `knowledge_question | small_talk | off_topic | prompt_injection`. When unsure, it leans to knowledge question. If the guard call fails, the message is treated as a knowledge question; grounding still applies.

**Follow-ups.** With chat history, the question is rewritten into a standalone search query ("what about lot 2?" → "What was the yield of lot LOT-V7-002?").

**Generation.** The model answers only from numbered excerpts, cites every factual sentence as `[n]`, treats excerpt text as untrusted data, prefers the newest source on conflict (R6), and names people exactly as written. Tokens stream to the browser through a **PII redactor** that holds back a short tail of text so an email or phone number split across chunks is still caught.

**Citation validation (R5).** After generation, the answer is split into claims (sentences and bullets):
- Markers pointing at excerpts that don't exist are removed. Markers the model put after the period or on the next line are moved back onto their sentence.
- **Re-attachment.** If a factual sentence has no marker, it is attached to the excerpt that clearly contains it: at least 60% of its content words (with light stemming) **and every number in it** must appear in that excerpt. Small models often forget markers on otherwise correct answers; this keeps those answers without loosening grounding, because a sentence with a number the excerpt doesn't contain can never be attached.
- Any factual claim still uncited is **dropped** and listed as removed. Users never see an uncited fact.
- If nothing factual survives, the answer becomes "I don't have enough information…".

**Confidence:**

```
confidence = 0.4·retrieval + 0.2·semantic_top3 + 0.3·citation_coverage + 0.1·has_support
retrieval  = best rerank score / 10 (or top cosine similarity without a reranker)
caps: nothing factual survives → ≤ 0.25;  answer cites facts but says part of the question
      isn't covered → ≤ 0.45;  top cosine < MIN_RETRIEVAL_SCORE (0.25) → ≤ 0.30
```

Below `CONFIDENCE_THRESHOLD` (0.55), the answer is marked *routed*, routing suggestions are added and a `low_confidence` gap is created for the review queue.

---

## 5. Routing and feedback (`feedback.py`)
- **Who:** candidates are the attendees, authors, reviewers and action-item owners of the retrieved sources. Each source contributes `1/(rank+1) + rerank/10` to each of its people, and the top `ROUTING_MAX_PEOPLE` (3) are suggested. People come only from parsed sources, never from the LLM.
- **Why:** a sentence naming the person's relation to the source ("author of …", "attended …", "owns action …"), plus the matched files with snippets.
- **Draft:** a short, polite LLM-written question for that person, falling back to a template. Editing and sending only logs it; nothing is delivered.
- **Corrections and rejections** create `gaps` rows that keep the original question and answer. A rejection also produces routing. The review queue lists the gaps with their context; a team lead marks them reviewed or resolved with a note.

---

## 6. Observability (`metrics.py`) and evals (`evals.py`)
- **Per answer:** one `metrics` row with status, guardrail category, latency, time to first token, top semantic score, top rerank score, citation count, citation validity, uncited drops, PII redactions and confidence.
- **Rollups** for 24h / 7d / 30d compare each metric with the previous window. **Alerts** fire on absolute thresholds (`ALERT_*`: answer rate, mean confidence, citation validity, negative feedback, p95 latency) and on a relative drop against the previous window (`ALERT_BASELINE_DROP_PCT`). Small windows are suppressed (`ALERT_MIN_SAMPLES`) so one bad answer doesn't page anyone.
- **Evals** run the full answer pipeline without saving anything. They score:
  - **Retrieval:** hit rate and MRR against the expected source files, plus whether the answer cites an expected source.
  - **Behaviour:** answerability (confident on answerable questions, routes or refuses unanswerable ones) and keyword recall.
  - **LLM judge:** faithfulness and relevance.
- **Faithfulness** is judged **per claim** against the **full text** of the chunks each claim cites, and asks only "do these excerpts state this?". The score is the share of supported claims. Completeness is scored separately as relevance. An earlier version graded the whole answer against 600-character previews, which marked correct facts as unsupported.
- The golden set (`backend/eval/golden.jsonl`) is hand-written. The synthetic set is generated by the LLM from random chunks (`--synthesize N`).

---

## 7. Models and configuration (`llm.py`, `config.py`)
- Any LangChain provider works through `init_chat_model` / `init_embeddings`. `openai`, `google_genai` and `ollama` are installed; others need `uv add langchain-<provider>`.
- Structured output uses the method that works best for the provider (`LLM_STRUCTURED_OUTPUT=auto`).
- `LLM_MAX_RPM` adds a client-side rate limiter for free tiers such as Gemini's 15 requests/minute.
- `nomic-embed-text` gets its required `search_query:` / `search_document:` prefixes automatically.
- A missing API key or an unreachable provider returns HTTP 503 with a clear message.
- All tunables live in `config.py` and are read from `backend/.env`; `.env.example` lists them with defaults.

| Setting | Default | Why |
|---|---|---|
| `CHUNK_MAX_TOKENS` / `CHUNK_MIN_TOKENS` / `CHUNK_OVERLAP_TOKENS` | 512 / 80 / 64 | §2.4 |
| `CANDIDATE_K` / `RERANK_TOP_N` / `TOP_K` | 20 / 10 / 6 | Wide recall, then precision; the rerank cost is bounded at 10 calls |
| `RRF_K` | 60 | Standard RRF constant (§3) |
| `CONFIDENCE_THRESHOLD` | 0.55 | An answer must have both a relevant passage and most of its claims cited. Weak retrieval (rerank ≤ 3) with half the claims uncited lands near 0.5 and is routed. A heuristic, to calibrate with the golden eval |
| `MIN_RETRIEVAL_SCORE` | 0.25 | Below this cosine similarity, nothing in the corpus is really about the question |
| `HISTORY_MESSAGES` | 6 | Three turns are enough to resolve "that", "it" and "lot 2" |

---

## 8. Storage schema (`schema.sql`)
`documents`, `action_items`, `enrichment_cache`, `conversations`, `messages` (each answered query is an assistant message whose id is the query id, holding the final payload), `routing_suggestions`, `gaps` (`low_confidence | rejected | correction`, `pending | reviewed | resolved`), `metrics`, `eval_runs`, `eval_results`. `init_db()` adds new columns to existing databases when the schema grows.

## 9. Known limits
- No authentication: names are free text, and routed questions are logged, not sent.
- Latency is dominated by the LLM. Each question costs a guard call, up to 10 rerank calls and an answer (about 40 s on local `qwen2.5:7b`). `RERANKER=none` and `GUARDRAILS_LLM=false` trade quality for speed.
- Legacy `.doc/.ppt/.xls` need LibreOffice on the host.
- The confidence formula and threshold are heuristics; calibrate them with the golden eval whenever the models change.
