---
name: feedback-no-fake-models
description: No fake/mock LLM or embedding providers; real LangChain providers only
metadata:
  node_type: memory
  type: feedback
  originSessionId: 2ca11ca8-02f9-45c3-94f0-962e1f21217c
  modified: 2026-10-05T16:18:27.268Z
---

Model providers are real LangChain providers selected in backend/.env: `openai` (gpt-4o-mini, text-embedding-3-small), `google_genai` (gemini-3.1-flash-lite, gemini-embedding-001), local `ollama` (qwen2.5:7b, nomic-embed-text), or any other via `uv add langchain-<provider>`. Tests use real local Ollama (integration test skips if unavailable). Chunking must be structure-aware recursive, not fixed-size.

**Why:** the user rejected fake models and fixed 1000-char chunking. **How to apply:** never add Fake*Model/DeterministicFakeEmbedding; keep the factory the only place clients are built.

Related: [[project-status]]
