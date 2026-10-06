# Seed index

A pre-built, chat-free copy of the index for the files in `data/`, so a fresh checkout or container works without re-ingesting.

| File | Contents |
|---|---|
| `app.db` | SQLite with source data only: 40 documents with derived metadata, 71 action items and the enrichment cache. No conversations, feedback, gaps, metrics or eval runs |
| `chroma/` | One Chroma collection, `fastchip__google-genai-gemini-embedding-001` (176 chunks) |

- On startup the backend copies this folder into `backend/storage/` **only if storage is empty** (`seed_storage()` in `app/main.py`). Existing local data is never overwritten.
- The vectors are Gemini embeddings (`gemini-embedding-001`). With another embedding model the app uses a different collection, so run **Ingest changes** once.
- Regenerate it after `data/` changes: ingest with the Gemini preset, clear the chat tables, and copy `app.db` plus the Gemini collection here.
