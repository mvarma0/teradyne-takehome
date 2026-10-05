# FastChip Knowledge System

A RAG knowledge system for the fictional FastChip Semiconductor, built as a take-home assignment in three exercises:

1. **Meetings**: ingest meeting transcripts, derive structured metadata and expose a natural-language query API.
2. **Office docs**: add .docx/.pptx/.xlsx with source and author traceability, low-confidence routing, correction and gap capture, and quality instrumentation.
3. **Web app**: a React UI with per-claim citations, metadata badges, an editable routing panel and a team-lead review queue.

The assignment brief is in [`take-home-assignment.md`](take-home-assignment.md). The step-by-step plan and current progress are in [`TASKS.md`](TASKS.md). Architecture, schemas and design rules are in [`CLAUDE.md`](CLAUDE.md).

## Stack
FastAPI (uv, Python 3.12) · LangChain · ChromaDB · SQLite · OpenAI `gpt-4o-mini` / `text-embedding-3-small` · React + Vite + TypeScript + Tailwind

## Running locally
Backend (from `backend/`):
```bash
uv sync
cp .env.example .env          # set OPENAI_API_KEY
uv run uvicorn app.main:app --reload   # http://localhost:8000/api/health
uv run pytest                 # offline tests
```

Frontend (from `frontend/`):
```bash
npm install
npm run dev                   # http://localhost:5173, proxies /api to :8000
```

## Status
Work in progress. See the checkboxes in [`TASKS.md`](TASKS.md).
