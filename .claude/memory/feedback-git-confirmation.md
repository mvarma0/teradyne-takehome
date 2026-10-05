---
name: feedback-git-confirmation
description: Always ask before committing/pushing; run a secret/sensitive-data scan before any push
metadata:
  node_type: memory
  type: feedback
  originSessionId: 2ca11ca8-02f9-45c3-94f0-962e1f21217c
  modified: 2026-10-05T16:18:18.481Z
---

Get explicit confirmation before every git commit and every push; one approval doesn't carry to the next. Before pushing, scan staged files for secrets/tokens/passwords/personal data, and confirm `.env`, `backend/storage/`, and `.claude/settings.local.json` stay out (a cleaned `.claude/settings.json` with only plugin toggles is committed by user choice). Use the commit message the user specifies.

**Why:** the repo is public and shared externally; the user asked for confirmation gates and leak checks. **How to apply:** show what will be committed, scan, ask, then commit/push.

Related: [[project-status]]
