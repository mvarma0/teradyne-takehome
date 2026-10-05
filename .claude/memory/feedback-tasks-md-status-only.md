---
name: feedback-tasks-md-status-only
description: "In TASKS.md only update statuses ([x]/[~]/[ ]) and add notes; never remove or rewrite task content"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 2ca11ca8-02f9-45c3-94f0-962e1f21217c
  modified: 2026-10-05T16:18:21.205Z
---

When updating TASKS.md, change only status markers (`[x]` done, `[~]` in progress, `[ ]` to do) and append "Status:" notes or new items. Never delete or replace existing task descriptions.

**Why:** I once rewrote the Exercise 2/3 sections wholesale and the user objected; the file was restored from git. **How to apply:** after editing, `git diff TASKS.md` should show only marker swaps as deletions.

Related: [[project-status]]
