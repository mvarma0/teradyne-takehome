# Take-Home Assignment: FastChip Knowledge System

A retrieval-augmented generation (RAG) knowledge system for a fictional semiconductor company. It is built in three exercises, and each one extends the previous one.

> **What this file is:** my own working spec, written by me on top of the original brief ([PDF](docs/Teradyne_FDE_Take-Home_Exercises.pdf)). It restates the three exercises and adds my choices: the invented company, the technology stack and the initial API. The PDF also sets the workspace, AI-tool and data rules (for example, *"You generate your own dataset"*).

| # | Exercise | Focus | Deliverable |
|---|---|---|---|
| 1 | Meeting transcripts | Ingestion, enrichment, query API | Working service, callable via curl or a test script |
| 2 | Office documents | Traceability, routing, gap capture, instrumentation | Working system over both sources behind a single API |
| 3 | User-facing application | Web UI, review queue, measurement | Working app plus a one-paragraph measurement approach |

---

## Exercise 1: Meeting Transcripts

**Ingestion, enrichment and query API**

### Data
A corpus of meeting transcripts for the imagined organization, in Markdown. Each transcript includes:
- attendees
- date
- free-form conversational text with decisions and action items embedded in it

### Requirements
Build a service that:
1. **Ingests** the transcript folder.
2. **Derives structured metadata** per transcript:
   - topic domain
   - priority, where applicable
   - attendees, preserved exactly from the source
3. **Stores** the results in a structured, queryable format.
4. **Exposes a query API** that accepts a natural-language query and returns relevant results with their derived metadata.

### Deliverable
- A working service that runs locally and can be called via `curl` or a test script.

---

## Exercise 2: Office Documents

**Traceability and routing**

### Data
Office documents from the same organization, ingested alongside the Exercise 1 transcripts:

| Format | Extensions |
|---|---|
| Word | `.doc` / `.docx` |
| PowerPoint | `.ppt` / `.pptx` |
| Excel | `.xls` / `.xlsx` |

### Requirements
- **Unified querying:** both sources can be queried through a **single API**, and business rules apply consistently across them.
- **Traceability:** every piece of information surfaced (query response, citation, routing suggestion) traces back to its **source file** and its **author or attendees**.
- **Routing:** when the system can't answer confidently, it uses traceability to suggest:
  - **who** to ask
  - **why** (what content matched)
  - a **drafted question** for that person
- **Corrections and rejections:** when a consumer corrects or rejects an answer, the correction is captured **with the original query**.
- **Gap retrieval:** gaps and corrections can be retrieved through the API.
- **Instrumentation:** quality degradation is caught **before users notice**.

### Deliverable
- A working system with both sources behind a single API, traceability live, routing functional and gap capture operational.

---

## Exercise 3: User-Facing Application

### Requirements
A web application that puts the full system in front of a user:
- The user asks a question in plain language and gets an answer with **visible citations showing the source file and author for each claim**.
- **Derived metadata** appears alongside the results.
- When the system can't answer confidently, the interface presents the **suggested routing** (who, why, draft question) ready for the user to **review, edit and send**.
- Gaps and corrections captured through the interface appear in a **simple review queue** that a team lead could check periodically.

### Deliverables
- **A working application** that runs locally. React is preferred but not required.
- **A measurement approach:** one metric to track for the first 30 days after launch and how to measure it, in one paragraph at most.

---

## Company Context: FastChip Semiconductor *(fictional)*

| | |
|---|---|
| **Size** | Mid-size, about 500 employees |
| **Locations** | HQ in Austin, TX · design center in Portland, OR · test facility in Penang, Malaysia |
| **Products** | Automotive-grade microcontrollers (MCUs) and power-management ICs |
| **Current situation** | Ramping production of **Falcon-7**, the next-gen automotive MCU, while managing yield issues on the existing **Eagle-5** line |
| **Key challenges** | Yield optimization · automotive qualification (AEC-Q100) · customer deadlines · supply chain coordination |

### Departments and Key People

| Department | Name | Role |
|---|---|---|
| Engineering | Sarah Chen | VP Engineering |
| Engineering | Marcus Rivera | Sr. Process Engineer |
| Engineering | Priya Patel | Design Lead |
| Engineering | James Kim | Test Engineer |
| Operations | David Park | VP Operations |
| Operations | Lisa Wong | Supply Chain Manager |
| Operations | Tom Bradley | Fab Manager |
| Product / Business | Rachel Adams | Product Manager |
| Product / Business | Mike O'Brien | Sales Director |
| Product / Business | Jennifer Liu | Quality Manager |
| Leadership | Robert Zhang | CEO |
| Leadership | Amanda Foster | CTO |
| Leadership | Kevin Nash | CFO |

---

## Dataset

The PDF asks candidates to generate their own dataset. I generated it **outside this workspace** and committed it to `data/`. Later changes (Office files rebuilt as real OOXML, contradictions fixed, 4 meetings and a company overview added, dates shifted to 2026) are listed in [`CLAUDE.md`](CLAUDE.md#dataset-in-data-read-only). The application only ingests `data/` and never modifies it, except for files a user uploads through the UI.

The data tells one story, January → September 2026: the **Volta-7** automotive EV powertrain controller, from first-silicon yield problems through an HTOL reliability failure, a design fix and customer (NovaDrive Motors) qualification, to production and the FY2027 strategy. The company overview ties it to FastChip's other product lines (Eagle-5, Falcon-7, PowerLine).

### Meeting transcripts: `data/meetings/` (24 × `.md`)

| Period | Themes |
|---|---|
| Jan 2026 | Ramp kickoff, first yield data, ATE test program, design-to-PE handoff |
| Feb 2026 | Metal-layer yield defect, CMP slurry supplier, reliability test plan, NovaDrive sample escalation, test program complete |
| Mar 2026 | NPI status, HTOL failure review and emergency failure analysis, NovaDrive escalation, Rev B design fix and timeline risk |
| Apr 2026 | 8D corrective action review, Rev B first yield, reliability retest pass |
| May–Jun 2026 | NovaDrive audit prep and pass, lessons-learned retro, production ramp and supply, final 1000-hour HTOL readout |
| Sep 2026 | Annual strategy and Volta-8 roadmap |

### Office documents: `data/documents/` (16 files)

| Folder | Documents |
|---|---|
| `docx/` (6) | Corrective action 8D · Failure analysis (HTOL) · FastChip company overview · NPI checklist (Volta-7) · PE division SOP · Yield improvement report Q1 |
| `pptx/` (5) | NovaDrive audit readout · Quarterly PE review Q1 · Reliability qualification summary · Test coverage review · Volta-7 ramp status |
| `xlsx/` (5) | Action item tracker · Defect Pareto log · Reliability test matrix · Test time breakdown · Yield tracker |

---|---|
| 1-4 | Eagle-5 yield issues |
| 5-8 | Falcon-7 design reviews |
| 9-11 | Supply chain and vendor discussions |
| 12-14 | Customer escalation calls |
| 15-17 | Quality and compliance reviews |
| 18-20 | Executive strategy meetings |

### Office documents: `data/documents/` (15 files)

| Folder | Documents |
|---|---|
| `docx/` (5) | Eagle-5 Yield Analysis Report · Falcon-7 Design Spec · Quarterly Quality Report · Vendor Evaluation Summary · Customer Escalation Procedures |
| `pptx/` (5) | Falcon-7 Program Review · Eagle-5 Yield Improvement Plan · Q3 Business Review · Supply Chain Risk Assessment · AEC-Q100 Qualification Status |
| `xlsx/` (5) | Eagle-5 Yield Data by Wafer Lot · Falcon-7 Project Timeline & Milestones · Vendor Scorecard Matrix · Customer Complaint Tracker · Test Coverage Matrix |

---

## Technology Choices

| Layer | Choice |
|---|---|
| Backend API | Python + FastAPI, managed with **uv** |
| RAG framework | LangChain (document loaders, text splitters, chains, output parsers) |
| Vector store | **ChromaDB** for semantic retrieval |
| Structured store | **SQLite** for corrections, gaps, routing logs, quality metrics and the review queue |
| LLM | OpenAI `gpt-4o-mini` |
| Embeddings | OpenAI embeddings, or HuggingFace sentence-transformers for local use |
| Frontend | React + Vite + Tailwind CSS |

**Configurability:** every model and tunable (LLM, embedding model, chunking, retrieval, thresholds) is set through configuration, so switching models doesn't require code changes.

---

## API Surface (initial, extensible)

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/ingest` | Trigger the ingestion pipeline |
| `POST` | `/api/query` | Natural-language query → answer + citations + metadata |
| `POST` | `/api/query/{id}/correct` | Submit a correction for an answer |
| `POST` | `/api/query/{id}/reject` | Reject an answer (triggers routing) |
| `GET` | `/api/gaps` | List all gaps and corrections |
| `GET` | `/api/gaps/{id}` | Single gap detail |
| `GET` | `/api/review-queue` | Team-lead review queue |
| `PATCH` | `/api/review-queue/{id}` | Mark a queue item reviewed |

The full, final API is documented in [`CLAUDE.md`](CLAUDE.md#api).

---

## Development Approach

1. **Plan first.** [`CLAUDE.md`](CLAUDE.md) captures the full context: rules, stack, schemas and folder structure.
2. **Incremental tasks.** [`TASKS.md`](TASKS.md) breaks all three exercises into small numbered tasks in execution order. Each task has:
   - **Input:** what must already exist
   - **Files:** what it creates or modifies
   - **Accept:** acceptance criteria
   - **Verify:** a curl command, a test run or a manual check. A task isn't done until it's verified.
3. **Runnable checkpoints.** The system can be run and tested end to end after each exercise.
4. **Open decisions** are tracked at the end of `TASKS.md`.
