---
name: feedback-data-folder
description: "Don't read data/ contents unless asked; keep test fixtures small"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 2ca11ca8-02f9-45c3-94f0-962e1f21217c
  modified: 2026-10-05T16:20:31.247Z
---

- Don't read files under `data/` unless the user asks (they allowed reading one docx for the golden eval, and later the Office files to rebuild them).
- Keep test fixtures minimal ("don't waste tokens writing fixtures").

**Why:** explicit user instructions during the session. **How to apply:** test against `backend/tests/fixtures/` and generated mocks; ask before touching real data.

Related: [[project-status]]
