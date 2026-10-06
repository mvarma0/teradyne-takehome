<div align="center">

# 🔎 FastChip Knowledge System
### Ask questions over meetings and Office documents, and get answers you can trace

[![FastAPI](https://img.shields.io/badge/FastAPI-Python_3.12-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat&logo=react&logoColor=black)](https://react.dev)
[![LangChain](https://img.shields.io/badge/LangChain-RAG-1C3C3C?style=flat)](https://python.langchain.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Store-orange?style=flat)](https://www.trychroma.com)
[![SQLite](https://img.shields.io/badge/SQLite-Structured_Store-003B57?style=flat&logo=sqlite)](https://www.sqlite.org)

**Meeting transcripts + Word / PowerPoint / Excel → ask in plain language → cited answers, or the right person to ask**

</div>

---

## ✨ Features

| Feature | Description |
|---|---|
| 📄 **Two sources, one API** | Meeting transcripts (`.md`) and Office files (`.docx/.pptx/.xlsx`, legacy `.doc/.ppt/.xls` via LibreOffice) |
| 🏷️ **Derived metadata** | Topic, priority, products, summary, decisions and action items per source. Attendees and authors come only from the files, never from the model |
| 🔍 **Hybrid search** | Semantic (Chroma) + keyword (BM25), fused with RRF, then reranked by an LLM |
| 📌 **Cited answers** | Every claim cites its source file and author or attendees; uncited claims are removed |
| 🧭 **Routing** | When confidence is low: who to ask, why, and an editable draft question |
| 📝 **Corrections and gaps** | Corrections, rejections and low-confidence answers are saved with the original question in a review queue |
| 🧬 **Traceability** | Follow any answer from the question through retrieval scores, citations and confidence to where it ended up |
| ⬆️ **Upload** | Add or replace a document from the UI; only changed files are re-ingested |
| 📈 **Monitoring and evals** | Quality metrics against the previous period with alerts; golden and synthetic eval sets |
| 🛡️ **Guardrails** | Prompt-injection blocking, off-topic handling and PII redaction |
| 🔌 **Any model provider** | OpenAI, Gemini, local Ollama or any LangChain provider, switched in `.env` |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    React frontend (Vite + Tailwind)                  │
│  Ask · Documents · Traceability · Review queue · Monitoring · Evals  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ REST + Server-Sent Events (/api)
┌───────────────────────────────▼──────────────────────────────────────┐
│                           FastAPI backend                            │
│  ┌────────────┐  ┌────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ Ingestion  │  │ Retrieval  │  │  Answering  │  │ Feedback and  │  │
│  │ docling +  │  │ semantic + │  │ guardrails, │  │ routing, gaps,│  │
│  │ LLM enrich │  │ BM25 + RRF │  │ citations,  │  │ metrics,      │  │
│  │ + chunking │  │ + rerank   │  │ confidence  │  │ evals         │  │
│  └─────┬──────┘  └─────┬──────┘  └──────┬──────┘  └──────┬────────┘  │
│        ▼               ▼                ▼                ▼           │
│   ┌─────────┐    ┌──────────┐    ┌──────────────────────────────┐    │
│   │  data/  │    │ ChromaDB │    │ SQLite: documents, messages, │    │
│   │ sources │    │ vectors  │    │ routing, gaps, metrics, evals│    │
│   └─────────┘    └──────────┘    └──────────────────────────────┘    │
│              LLM + embeddings via LangChain (provider set in .env)   │
└──────────────────────────────────────────────────────────────────────┘
```

**Pipeline**
1. **Ingest:** parse the file → read attendees/authors from the source → LLM enrichment → business rules → structure-aware chunks → Chroma + SQLite.
2. **Retrieve:** guardrails → rewrite follow-ups → semantic + BM25 → RRF fusion → LLM rerank.
3. **Answer:** stream a grounded answer → validate citations, drop uncited claims → score confidence.
4. **Route and learn:** low confidence → suggest people + draft question → gaps and corrections → review queue → metrics.

---

## 🚀 Quick start

### Prerequisites
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 18+
- One model provider: an OpenAI or Gemini API key, **or** [Ollama](https://ollama.com) running locally (free)

### 1. Configure

```bash
cd backend
uv sync
cp .env.example .env
```

Open `backend/.env` and keep **one** preset uncommented: A (OpenAI, add `OPENAI_API_KEY`), B (Ollama, no key) or C (Gemini, add `GOOGLE_API_KEY`). Nothing else is required. For Ollama, first run `ollama pull qwen2.5:7b && ollama pull nomic-embed-text`.

### 2. Install the frontend

```bash
cd ../frontend
npm install
```

### 3. Run

```bash
cd ..
./dev.sh            # backend on :8000 and frontend on :5173
```

### 4. Load the data and ask

Open **http://localhost:5173** → **Documents** → **Ingest changes** (or `curl -X POST localhost:8000/api/ingest`), then ask a question on **Ask**. 🎉

API docs (Swagger): http://localhost:8000/docs

---

## 🖥️ Using the app

| Page | What it's for |
|---|---|
| **Ask** | Chat with streamed answers. Hover a citation number for the source; click to open the passage. Rate, correct or reject answers |
| **Documents** | Every indexed source with its metadata. **Upload** a new or updated file, or re-ingest |
| **Traceability** | For any answered question: guardrail result, search query, retrieved passages with scores, which were cited, kept and dropped claims, confidence, routing and gaps |
| **Review queue** | Low-confidence answers, rejections and corrections for a team lead to review or resolve |
| **Monitoring** | Answer rate, confidence, citation validity, feedback and latency against the previous window, with alerts |
| **Evals** | Run golden and synthetic question sets and track quality over time |
| **About** | What the system does and how to use it |

---

## 🔧 Tech stack

**Backend:** FastAPI · uv · LangChain · docling · ChromaDB · rank-bm25 · SQLite · pydantic-settings

**Models (pick in `.env`):** OpenAI `gpt-4o-mini` + `text-embedding-3-small` · Gemini `gemini-3.1-flash-lite` + `gemini-embedding-001` · Ollama `qwen2.5:7b` + `nomic-embed-text`

**Frontend:** React 19 · Vite · TypeScript · Tailwind v4 · react-router · react-markdown · recharts

---

## 📁 Project structure

```
├── backend/
│   ├── app/                # flat: one module per concern
│   │   ├── main.py         # FastAPI app
│   │   ├── config.py       # every setting (read from .env)
│   │   ├── llm.py          # the only place model clients are built
│   │   ├── loaders.py      # meetings + Office files → documents (people from the source)
│   │   ├── ingest.py       # enrichment, chunking, ingestion pipeline (+ CLI)
│   │   ├── rules.py        # business rules
│   │   ├── search.py       # Chroma + BM25 → RRF → LLM rerank
│   │   ├── guardrails.py   # injection, topic, PII
│   │   ├── answer.py       # chat flow, citation checks, confidence
│   │   ├── feedback.py     # routing (who to ask) + correct / reject / rate
│   │   ├── metrics.py      # monitoring and alerts
│   │   ├── evals.py        # golden + synthetic evaluation (+ CLI)
│   │   ├── api.py          # HTTP routes
│   │   ├── db.py, schema.sql, schemas.py
│   ├── eval/golden.jsonl
│   ├── scripts/            # curl smoke tests for Ex1 and Ex2
│   └── tests/
├── frontend/src/
│   ├── pages/              # Ask, Documents, Trace, Review, Monitoring, Evals, About
│   ├── components/         # chat, citations, metadata badges, charts, UI kit
│   └── api/client.ts
├── data/                   # meetings/ and documents/ (the corpus)
├── docs/MEASUREMENT.md     # the 30-day metric
├── DELIVERABLE.md          # each requirement and where it is met
├── TECH.md                 # technical design: chunking, retrieval, citations, evals
└── dev.sh
```

---

## 🧪 Tests

```bash
cd backend
uv run pytest -m "not integration"                    # fast unit tests
uv run pytest                                         # + end-to-end against local Ollama (skipped if unavailable)
./scripts/smoke_ex1.sh && ./scripts/smoke_ex2.sh      # curl checks against a running server
uv run python -m app.evals --dataset golden           # retrieval and answer quality
cd ../frontend && npm run build                       # type-check + build
```

---

## 📚 More docs

| Doc | Contents |
|---|---|
| [`DELIVERABLE.md`](DELIVERABLE.md) | Every requirement from the brief, how it's met and where |
| [`TECH.md`](TECH.md) | Technical design: parsing, chunking (why 512 tokens), hybrid retrieval, citation checks, confidence, routing, evals |
| [`backend/README.md`](backend/README.md) | Providers, every setting, ingestion, every endpoint, troubleshooting |
| [`frontend/README.md`](frontend/README.md) | Frontend pages, structure and streaming |
| [`docs/MEASUREMENT.md`](docs/MEASUREMENT.md) | The 30-day measurement approach |
| [`take-home-assignment.md`](take-home-assignment.md) | The original brief ([PDF](docs/Teradyne_FDE_Take-Home_Exercises.pdf)) |
| [`TASKS.md`](TASKS.md) · [`CLAUDE.md`](CLAUDE.md) | Execution plan with per-task verification; architecture and rules |
| [`docs/AI_SESSION_LOG.md`](docs/AI_SESSION_LOG.md) | How it was built with [Claude Code](https://claude.com/claude-code), the primary AI tool |
