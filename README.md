# FastChip Knowledge System

A RAG knowledge system for the fictional FastChip Semiconductor, built as a take-home assignment in three exercises:

1. **Meetings**: ingest meeting transcripts, derive structured metadata and expose a natural-language query API.
2. **Office docs**: add .docx/.pptx/.xlsx alongside meetings, with every fact traceable to its source file and author or attendees. Includes low-confidence routing (who to ask, why, draft question), capture of corrections and gaps, and quality instrumentation.
3. **Web app**: a React chat app with streaming, guarded answers. It shows per-claim citations (hover for the source, click to open the document), derived metadata, an editable routing panel and a team-lead review queue. Extra pages cover Documents, Monitoring and Evals.

The original brief is [`docs/Teradyne_FDE_Take-Home_Exercises.pdf`](docs/Teradyne_FDE_Take-Home_Exercises.pdf), restated in [`take-home-assignment.md`](take-home-assignment.md). The plan and progress are in [`TASKS.md`](TASKS.md). Architecture, schemas and rules are in [`CLAUDE.md`](CLAUDE.md). The 30-day metric is in [`docs/MEASUREMENT.md`](docs/MEASUREMENT.md). How the project was built with Claude Code (decisions, corrections, verification) is in [`docs/AI_SESSION_LOG.md`](docs/AI_SESSION_LOG.md); the session context Claude kept (memory and plans) is in [`.claude/`](.claude/).

## AI tooling
**Primary AI tool: [Claude Code](https://claude.com/claude-code) (CLI).** It was used throughout for planning, implementation and verification. The workspace keeps its context: `CLAUDE.md` (project rules), `TASKS.md` (plan with per-task verification), `.claude/` (memory and plans) and `docs/AI_SESSION_LOG.md` (how the sessions went). LangChain is used inside the solution, orchestrated from code.

## Stack
FastAPI (uv, Python 3.12) · LangChain · docling · ChromaDB + BM25 · SQLite · Pluggable model providers via LangChain: OpenAI (`gpt-4o-mini`, `text-embedding-3-small`), Google Gemini (`gemini-3.1-flash-lite`, `gemini-embedding-001`), local Ollama (`qwen2.5:7b`, `nomic-embed-text`) or any other LangChain provider · React 19 + Vite + TypeScript + Tailwind

## Quick start
```bash
# 1. Backend config: choose a provider: OpenAI, Google Gemini, Ollama or any LangChain provider (see backend/README.md)
cd backend && uv sync && cp .env.example .env && cd ..
# 2. Frontend deps
cd frontend && npm install && cd ..
# 3. Run both
./dev.sh                                   # API http://localhost:8000/docs · App http://localhost:5173
# 4. Ingest data/ (or use "Ingest" on the Documents page)
curl -X POST localhost:8000/api/ingest
```
Then open http://localhost:5173 and ask a question.

Full backend guide (providers, ingestion, every endpoint, troubleshooting): [`backend/README.md`](backend/README.md). Frontend guide (run, pages, folder structure, streaming): [`frontend/README.md`](frontend/README.md).

## What's in the app
| Page | What it does |
|---|---|
| **Chat** | Multi-turn conversation with streamed answers. Follow-ups are rewritten using the chat history. Inline citation chips: hover shows the source file, author or attendees, date and snippet; click opens the document with the cited passage highlighted. Topic, priority and products appear with each answer, alongside a confidence meter. Filters cover topic, source type, priority, person and date range. Answers can be rated, corrected or rejected. |
| **Routing panel** | When confidence is low, or an answer is rejected, it shows who to ask, why (the matched files) and an editable draft question to send. Sending is logged only. |
| **Review queue** | Low-confidence answers, rejections and corrections, each with the original question, answer, routing and sources. Items can be marked reviewed or resolved with a note. |
| **Documents** | Every ingested meeting and document with its derived metadata, with search, filters and an ingest button. The viewer shows people with roles, summary, decisions, action items, chunks and the business rules applied. |
| **Monitoring** | Answer rate, confidence, citation validity, negative feedback, latency, retrieval score and guardrail activity. Each is compared with the previous window, with alerts and trend charts. |
| **Evals** | Golden and synthetic question sets measuring hit rate, MRR, faithfulness, answer relevance, answerability and keyword recall. Shows per-case results and the trend across runs. |

## Guardrails
- **Prompt injection:** blocked by heuristics plus an LLM classifier.
- **Off-topic:** politely declined.
- **Grounding:** every claim must cite a retrieved excerpt; invalid markers are removed and uncited claims dropped. Retrieved text is treated as untrusted data.
- **Low confidence:** the system routes the question to people instead of guessing.
- **PII:** emails, phone numbers and similar are redacted, including on the live token stream.

## Tests
```bash
cd backend
uv run pytest                    # unit + end-to-end against local Ollama (skipped if Ollama is unavailable)
./scripts/smoke_ex1.sh && ./scripts/smoke_ex2.sh   # against a running server
uv run python -m app.evals --dataset golden
cd ../frontend && npm run build
```
