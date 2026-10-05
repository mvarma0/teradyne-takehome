---
name: feedback-no-fake-models
description: No fake/mock LLM or embedding providers; only openai or local ollama
metadata:
  node_type: memory
  type: feedback
  originSessionId: 2ca11ca8-02f9-45c3-94f0-962e1f21217c
  modified: 2026-10-05T16:18:27.268Z
---

Model providers are `openai` (gpt-4o-mini, text-embedding-3-small) or local `ollama` (qwen2.5:7b, nomic-embed-text), selected in backend/.env. Tests use real local Ollama (integration test skips if unavailable). Chunking must be structure-aware recursive, not fixed-size.

**Why:** the user rejected fake models and fixed 1000-char chunking. **How to apply:** never add Fake*Model/DeterministicFakeEmbedding; keep the factory the only place clients are built.

Related: [[project-status]]
