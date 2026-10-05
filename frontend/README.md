# FastChip Knowledge Assistant (frontend)

A React web app for the FastChip RAG system. Users ask questions in plain language and get streamed answers with citations to the source file and its author or attendees. When the system isn't confident, it suggests who to ask. Corrections and rejections flow into a team-lead review queue, and there are extra pages for documents, monitoring and evals.

**Stack:** React 19 · TypeScript · Vite · Tailwind CSS v4 (+ typography) · react-router · react-markdown (+ GFM) · recharts · lucide-react

---

## Prerequisites
- Node.js 20+ (developed on Node 24)
- The backend running on `http://localhost:8000` (see [`../backend/README.md`](../backend/README.md)), with data ingested

## Run
```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```
Or start the backend and frontend together from the repo root with `./dev.sh`.

The dev server proxies every `/api/*` request to `http://127.0.0.1:8000` (`vite.config.ts`), so no CORS setup or environment variables are needed. The proxy target is `127.0.0.1` rather than `localhost` because Node resolves `localhost` to IPv6, while uvicorn listens on IPv4.

## Scripts
| Command | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload on :5173 |
| `npm run build` | Type-check (`tsc -b`) + production build to `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | Lint with oxlint |

---

## Pages
| Route | Page | Highlights |
|---|---|---|
| `/chat`, `/chat/:conversationId` | **Chat** | Conversation sidebar (persisted server-side) and streamed answers with stage indicator and typing caret. Follow-up questions keep the context; a stop button and filters (topic, source type, priority, person, date range) sit in the composer. |
| (in Chat) | **Citations** | Inline `[n]` chips. Hover shows the source card: file, author or attendees, date, section, snippet, metadata. Click opens a document drawer with the cited chunk highlighted. |
| (in Chat) | **Answer metadata** | Confidence meter, topic, priority and products of the cited documents, a note when unsupported statements were removed, PII and guardrail badges. |
| (in Chat) | **Routing panel** | Shown on low confidence or after a rejection: who, role, why (matched files) and an editable draft question with Send (logged), Copy and Dismiss. |
| (in Chat) | **Feedback** | Thumbs up/down; Correct and Reject dialogs (a rejection returns routing suggestions). |
| `/documents` | **Documents** | All ingested meetings and Office documents with derived metadata; search, type and topic filters; Ingest / Force re-ingest buttons with the ingest report. |
| `/documents/:docId?chunk=…` | **Document viewer** | People with roles, reviewers, summary, decisions, action items, chunks (the cited chunk is highlighted and scrolled into view), business rules applied, download original. |
| `/review` | **Review queue** | Counts; status and type filters; expandable gaps (original answer, correction or reason, routing and sent questions, sources); mark reviewed/resolved with a note; reopen; link back to the conversation. |
| `/monitoring` | **Monitoring** | 24h / 7d / 30d windows, alerts, KPI tiles compared with the previous window, trend charts, signal table. Auto-refreshes every 30s. |
| `/evals` | **Evals** | Run golden, synthetic or all sets; generate a synthetic set; runs list with live progress; summary vs targets; per-case table; quality trend across runs. |

The nav shows a pending badge for the review queue (polled every 15s). The theme toggle (light/dark) and the "Your name" field (sent as `submitted_by` / `sent_by`) are kept in `localStorage`.

---

## Folder structure
```
frontend/
├── index.html              # fonts (Inter, JetBrains Mono) + no-flash theme script
├── vite.config.ts          # React + Tailwind plugins, /api proxy → 127.0.0.1:8000
├── public/                 # favicon
└── src/
    ├── main.tsx            # React root
    ├── App.tsx             # router, app shell (nav rail, theme toggle, user name), lazy-loaded pages
    ├── index.css           # Tailwind setup, dark variant, brand colours, chart palette tokens, caret/highlight animations
    ├── types.ts            # TypeScript types mirroring the backend payloads
    ├── api/
    │   └── client.ts       # typed REST client (`api.*`) + `streamChat()` SSE parser
    ├── lib/
    │   └── format.ts       # % / ms / relative-time formatters, initials, user-name storage
    ├── components/
    │   ├── ui.tsx          # Button, Badge, Card, Modal, Spinner, EmptyState, ErrorBanner, PageHeader, inputClass
    │   ├── meta.tsx        # source-type icons, topic/priority/product badges, confidence meter
    │   ├── citations.tsx   # CitationChip (hover card), SourceCard, AnswerMarkdown, DocumentDrawer, DocumentBody
    │   ├── chat.tsx        # UserBubble, AssistantMessage, RoutingPanel, feedback bar, Composer (with filters)
    │   └── charts.tsx      # ChartCard, LineTrend, BarTrend, StatTile
    └── pages/
        ├── ChatPage.tsx
        ├── DocumentsPage.tsx
        ├── DocumentViewerPage.tsx
        ├── ReviewPage.tsx
        ├── MonitoringPage.tsx   # lazy-loaded (charts)
        └── EvalsPage.tsx        # lazy-loaded (charts)
```

---

## How streaming works
`streamChat()` in `src/api/client.ts` POSTs to `/api/chat/stream` and parses Server-Sent Events from the response body. `ChatPage` handles each event:

| Event | UI effect |
|---|---|
| `conversation` | navigates to `/chat/:id` (new conversation) |
| `status` | stage indicator (checking → searching → writing → routing) |
| `guardrail` | blocked or off-topic notice |
| `sources` | citations become available, so chips render while tokens stream |
| `token` | appends text (already PII-redacted by the backend) |
| `final` | replaces the streamed text with the **validated** answer (uncited claims removed) plus confidence, routing and metadata |
| `error` | inline error |

The Stop button aborts the request through an `AbortController`.

## Backend endpoints used
`/api/chat/stream`, `/api/conversations[/{id}]`, `/api/query/{id}/correct|reject|feedback`, `/api/routing/{id}/send|dismiss`, `/api/review-queue[/{id}]`, `/api/documents[/{id}/content|file]`, `/api/ingest`, `/api/stats`, `/api/metrics`, `/api/evals[/run|/{id}|/synthesize]`. All of them are wrapped in `src/api/client.ts`.

---

## Conventions
- **Styling:** Tailwind utility classes only. Shared primitives live in `components/ui.tsx`. Dark mode is class-based (`.dark` on `<html>`; the `dark:` variant is defined in `index.css`).
- **Types:** `src/types.ts` mirrors the backend response shapes. Update it together with the backend models (`backend/app/models/api.py`, `answer/chat.py` payload). The tsconfig uses `verbatimModuleSyntax`, so import types with `import type`.
- **Charts:** recharts, coloured with the CSS tokens `--series-1..3`. These come from a validated colour-blind-safe palette with separate light and dark steps. Single-series charts use `--series-1`, multi-series charts get a legend plus direct labels, and dual y-axes are never used.
- **Citations:** answer text is markdown; `[n]` markers are turned into `#cite-n` links and rendered as `CitationChip`s by the markdown `a` renderer.

## Troubleshooting
| Symptom | Fix |
|---|---|
| "Request failed" / proxy errors in the terminal | The backend isn't running on :8000. Start it (`uv run uvicorn app.main:app --reload` in `backend/`). |
| Chat answers with 503 | The model provider isn't reachable or configured (missing `OPENAI_API_KEY`, or Ollama not running). Check `backend/.env`. |
| No sources / empty Documents page | Nothing ingested yet. Use **Ingest** on the Documents page. |
| Answers are slow | Local Ollama runs several model calls per answer; see the backend README for `RERANKER=none` / OpenAI. |
