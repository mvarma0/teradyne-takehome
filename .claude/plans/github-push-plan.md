# Plan: Push the workspace to GitHub

> **Snapshot:** the plan for the first push to GitHub, kept as written at the time. It is superseded by [`CLAUDE.md`](../../CLAUDE.md), [`TECH.md`](../../TECH.md) and [`TASKS.md`](../../TASKS.md). Work later moved to the `feature/configurable-llm-providers` branch.

## Context
The user wants the whole workspace checked in to GitHub for sharing. Nothing gets pushed until they explicitly confirm.

Current state, from read-only checks:
- The local repo is on `main`. The remote `origin` is `https://github.com/mvarma0/teradyne-takehome.git`.
- That remote is **already public**: the GitHub API returns 200 without auth. It holds `a1f64b8 Project scaffold`.
- Local is **1 commit ahead**: `c2aeba3`, the scaffold with the CLAUDE.md, TASKS.md, backend and frontend changes. The working tree is clean.
- 40 tracked files. A secret scan of tracked files found no API keys, and no `backend/.env` exists. `.env`, `.env.*`, `backend/storage/*`, `*.db`, `node_modules/`, `.venv/` and `dist/` are ignored.
- `.claude/settings.local.json` is excluded by your global gitignore (`~/.config/git/ignore`), so it won't be pushed. That's the right outcome, since it's machine-local.
- `data/` is empty, and git doesn't track empty directories, so it won't appear on GitHub yet.
- The `gh` CLI isn't installed. That's fine: a plain `git push` uses your existing credentials (the remote already received `a1f64b8`).

## Steps
1. **Pre-push review (read-only).** Show `git log origin/main..main --stat` and the final tracked file list, and re-run the secret scan. That way you see exactly what will become public.
2. **Ask for explicit confirmation** with the commit list, file count, target URL, and a reminder that the repo is public.
3. **On confirmation only:** `git push origin main`. No force push and no history rewrite.
4. **Verify:** `git status -sb` shows `main...origin/main` with nothing ahead, and `git ls-remote origin` shows HEAD = the local HEAD SHA. Open https://github.com/mvarma0/teradyne-takehome and check that README.md renders with CLAUDE.md and TASKS.md links.

## Going forward
- After each task or checkpoint: commit locally, then **ask before every push**. One approval doesn't carry over to the next push.
- When the dataset lands in `data/`, decide whether to commit it. It's needed to run the system, and it's fictional data, so committing it is likely fine. I'll ask at that point.

## Not doing
- No new repo creation, visibility changes, branch protection or force pushes.
