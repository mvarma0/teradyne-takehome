# Code review: `feature/configurable-llm-providers`

**Current status (after T1 fix, 2026-10-06): all findings are fixed.** That covers the original #1-#5, N1-N3
from the re-review and T1 from the third pass. Each fix has a regression test, and `pytest -m "not
integration"` passes (50 tests). The Ex2 smoke suite (12 checks) passes against the live server after the T1 fix.

Scope: committed range `main...HEAD` plus the uncommitted working-tree refactor (the `app/*` packages
collapsed into flat modules: `answer.py`, `api.py`, `db.py`, `ingest.py`, `loaders.py`, `search.py`, ...).

Checks run:
- Each module imports cleanly.
- `pytest -m "not integration"` passes (41 tests).
- No stale `app.ingestion` / `app.retrieval` / ... imports remain.
- The routes are registered in the same order as before.
- Every top-level function in the old packages was compared by AST with its new counterpart. The move
  is mechanical apart from the behaviour changes listed below.
- There are no name collisions in merged modules: `_converter`, `_DATE_RE`, `_TITLE_RE` and `_decode`
  were renamed correctly.

## Findings

| # | Location | Severity | Issue |
|---|---|---|---|
| 1 | `backend/app/guardrails.py:105` (used at `:120`) | high | The `_ABOUT_ASSISTANT` heuristic sends ordinary domain questions to the canned small-talk reply |
| 2 | `backend/app/answer.py:203` (with `_INSUFFICIENT` at `:33`) | medium | `partial` is set by any uncited sentence that matches `_INSUFFICIENT`, so complete answers get routed |
| 3 | `backend/app/answer.py:143` | low | `find_support` breaks ties toward the lowest-ranked excerpt |
| 4 | `backend/app/loaders.py:436` | low | The `_sheet_as_of` "date column" test is a substring match, so it also catches "Update", "Validated", ... |
| 5 | `backend/app/api.py:86-90` | low | An upload with an upper-case `.MD` extension is saved but never ingested |

### 1. Questions about tools and systems are answered with the canned greeting
`classify_input` runs `about_assistant()` before the LLM classifier. Its first alternative,
`\b(what|who|how)\b[^?]{0,40}\b(this|the|you|your)\s+(system|app|application|assistant|tool|bot|...)`,
matches any question that contains "the tool", "the system" or "the app". In a fab, those words are
part of normal work questions. I confirmed these all return `True`:
- "Who owns the tool qualification for the new CMP slurry?"
- "What caused the system failure on the ATE tester?"
- "How long was the tool down in March?"

Each one gets the `small_talk` canned reply with status `answered`. Retrieval never runs, and the
message is counted as a guardrail hit in the metrics. Fix: anchor the pattern to the assistant itself
("this system/app/assistant", "you"), or keep it only as a hint for the LLM classifier.

### 2. `partial` routes complete answers
`result.partial = bool(result.facts) and has_meta` caps confidence at 0.45, which marks the answer
as not confident. That creates a low_confidence gap and routes the question. "Meta" means any uncited
sentence that matches `_INSUFFICIENT`, and that pattern allows `no ... data|record|details|information`
within 60 characters. A factual sentence such as "Mike Chen noted there was no correlation with the
probe card data." is therefore classified as meta. I confirmed `partial=True` for an answer that has
a properly cited fact plus that sentence.

There is a second problem. `_classify` returns "meta" before the new `find_support` reattachment
runs, so this sentence is never reattached. It stays in the answer uncited, which goes against R5, and
it flips a good answer into "routed". Fix: match only first-person or sources-referencing phrasing
("the excerpts / documents / I ... don't ..."), or try `find_support` before classifying a sentence
as meta.

### 3. `find_support` breaks ties toward the lowest-ranked excerpt
`if score >= best_score` means that when several excerpts support an uncited claim equally (for
example two chunks of the same report, both at 1.0), the claim is attached to the last one, which
has the lowest rerank. Use `>` with the `MIN_SUPPORT` floor applied separately, so the
highest-ranked supporting excerpt wins.

### 4. `_sheet_as_of` treats "Update" and "Validated" columns as date columns
`"date" in h` is true for headers such as "Status Update", "Last Update", "Validated By" and
"Candidate". The cells in those columns are free text and go through `parse_date`, which calls
`dateparser.parse(..., fuzzy=True)`. Text like "moved to week 12" fuzzy-parses to the 12th of the
current month. That value can become the "latest" row date and is stored as the document date
(`date_basis="latest_row_date"`), so a spreadsheet can end up with a present-day or future date.
Fix: match `date` as a whole word, for example `re.search(r"\bdate\b", h)`, and parse only
`datetime` cells or ISO strings.

### 5. Uploads with an upper-case `.MD` extension are never ingested
The upload handler lower-cases the extension only to choose the folder, and saves the file under its
original name (for example `Notes.MD`). Meeting discovery uses `meetings_dir.rglob("*.md")`, which is
case-sensitive in Python 3.12 on POSIX, including macOS. The file is written into `data/meetings/`
and the response says the upload succeeded, but ingestion never picks it up. Office files are not
affected, because their discovery compares `p.suffix.lower()`. Fix: normalize the saved extension to
lower case, or make meeting discovery case-insensitive.

## Re-review after fixes (working tree, 2026-10-06)

Checks run: `pytest -m "not integration"` passes (46 tests, including the 5 new regression tests),
and each fix was probed with extra inputs from a Python shell.

| # | Status | How it was verified |
|---|---|---|
| 1 | Partly fixed | The three questions from the original report now return `False`, and the new test covers them. The second alternative (`what can you do`, `who are you`, `how do I use this/it/you`) is still only anchored at the start, so it over-matches. See N1. |
| 2 | Fixed (with a new side effect) | `_INSUFFICIENT` now needs first-person or sources-referencing phrasing. "...showed no correlation with the probe card data." is reattached to its excerpt as a cited fact, and `partial=False` (see `test_negative_fact_is_not_a_missing_information_statement`). Reattachment now runs before classification, which causes N2. |
| 3 | Fixed | `score > best_score or (best is None and score == best_score)` keeps the first excerpt when scores tie. `find_support(text, [text, text]) == 1`. |
| 4 | Fixed | The header must contain `date` as a whole token (`^`, whitespace, `_`, `-` or `/` on both sides). "Status Update" and "Validated By" are ignored. The test sheet returns `2026-03-02`. Fuzzy parsing of free text inside real `Date` columns was left as is. That part of the suggestion was optional. Small regression: see N3. |
| 5 | Fixed | The saved name gets a lower-case extension (`Weekly_Sync.MD` is saved as `meetings/Weekly_Sync.md`, and the new test checks that). The suffix has the same length before and after lower-casing, so the slice is safe. |

### New findings

| # | Location | Severity | Issue |
|---|---|---|---|
| N1 | `backend/app/guardrails.py:109-110` | medium | The second `_ABOUT_ASSISTANT` alternative still sends domain questions to the canned reply |
| N2 | `backend/app/answer.py:187-191` | medium | Reattaching before classifying turns "the documents don't mention X" into a cited fact, so `partial` and routing are skipped |
| N3 | `backend/app/loaders.py:436` | low | The new header pattern misses `Date:`, `Dates` and `Date(UTC)` |

#### N1. "How do I use this checklist ...?" is still answered with the canned greeting
`^\s*(?:what can you do|who are you|what are you|how (?:do|can|should) (?:i|we) use (?:this|it|you))\b`
has no end anchor. Any question that starts with one of these phrases matches. I confirmed these
all return `True`:
- "How do I use this checklist for the NPI gate review?"
- "How should we use this SOP when a lot fails?"
- "What can you do about the Eagle-5 yield loss?"
- "Who are you assigning the 8D to?"

Each one gets the small_talk reply, and retrieval never runs. Questions about how to use an SOP or
checklist are core use cases for this corpus. Fix: anchor this alternative at the end the same way as
the first one, e.g. `(?:this|it|you)\s*[?.!]*\s*$`. You could also allow a short tail such as
"for", but never an arbitrary noun phrase.

#### N2. Reattaching before classifying hides "not covered" statements
`build_claims` now calls `find_support` on every uncited sentence before `_classify`. `find_support`
only measures overlap between content words. It ignores negation and the "documents don't
mention" framing. When the answer says "The documents do not mention the NovaDrive audit budget
for the Volta-7 line in Penang." and an excerpt talks about that audit, the sentence gets `[2]`.
It is then classified as a **fact** rather than meta. I confirmed this: `partial=False`, and the
claim is shown as `fact` with citation `[2]`. So in exactly the case fix #2 was meant to route (the
answer says part of the question isn't covered), confidence is no longer capped at 0.45, no routing
happens, and a statement about missing information is shown as a sourced claim. Now that
`_INSUFFICIENT` is narrow enough not to catch negative facts, the order change isn't needed. Fix:
check `_INSUFFICIENT` first and skip reattachment for sentences that match it, or go back to
"classify, then reattach only `fact`".

#### N3. Some ordinary date headers are no longer recognised
`(?:^|[\s_\-/])date(?:$|[\s_\-/])` requires whitespace, `_`, `-`, `/` or the end of the string
after `date`. "Date:", "Log Date.", "Dates" and "Date(UTC)" now return `False`, but the old
substring test matched them. A sheet whose only date column is headed like this loses its as-of date
and is stored undated. Fix: use word boundaries, e.g. `r"\bdates?\b"`. `\b` treats `_` as a word
character, so also normalise `_` to a space first, or keep the `_` alternative.

## Third pass (working tree, 2026-10-06)

Checks run: `pytest -m "not integration"` passes (49 tests, including the new tests
`test_assistant_phrases_must_end_the_question`, `test_not_covered_statement_is_never_cited_as_a_fact`
and `test_sheet_as_of_accepts_date_header_variants`). Each fix was also probed with extra inputs from a
Python shell.

| # | Status | How it was verified |
|---|---|---|
| N1 | Fixed | The second alternative now ends with `\s*[?.!]*\s*$`. All four N1 questions ("How do I use this checklist for the NPI gate review?", "How should we use this SOP when a lot fails?", "What can you do about the Eagle-5 yield loss?", "Who are you assigning the 8D to?") return `False`. "what can you do?", "who are you" and "How do I use it?" still return `True`. |
| N2 | Fixed | `build_claims` skips `find_support` when `_INSUFFICIENT` matches (`answer.py:192`). "The documents do not mention the NovaDrive audit budget for the Volta-7 line in Penang." with an excerpt about that audit stays `meta` with no citation, and `partial=True`, so the answer routes. A negative fact ("...no correlation with the probe card data.") is still not treated as meta. |
| N3 | Fixed | `(?:^\|[^a-z])dates?(?:$\|[^a-z])` accepts "Date:", "Dates", "Date(UTC)", "Log Date.", "start_date", "date_logged" and "Date Updated". It still rejects "Update", "Status Update", "Validated By", "Candidate", "Mandate" and "Due Date". |
| #1 | Mostly fixed (see T1) | Both alternatives are now anchored to the end of the question. The three original questions and the N1 questions all return `False`. But the first alternative still lets up to 30 arbitrary characters sit between the question word and "this tool/system/app", so some domain questions still match. |

### New findings

| # | Location | Severity | Issue |
|---|---|---|---|
| T1 | `backend/app/guardrails.py:105-107` (used at `:121`) | low | "Who owns this tool?" and similar fab follow-ups still get the canned small-talk reply |

#### T1. "<question word> ... this tool/system?" is still treated as a question about the assistant
The first alternative is `^\s*(?:what|who|how)\b[^?]{0,30}?\b(?:this|you|your)\s+(?:system|app|...|tool|...)...$`.
The `[^?]{0,30}?` gap accepts any verb, so these all return `True`:
- "Who owns this tool?"
- "Who maintains this tool?"
- "How reliable is this tool?"
- "What's the status of this tool?"
- "How old is this system?"

In a fab, "this tool" usually means a process or test tool. These questions are also likely as
follow-ups: after "What happened with the CMP polisher in Penang?", the user asks "Who maintains this
tool?". `classify_input` runs the heuristic on the raw message before the follow-up is condensed with
history, so the user gets the canned greeting and retrieval never runs. Severity is low because the
standalone question is ambiguous, but the history makes the intent clear and the heuristic ignores it.
Fix: allow only a fixed set of verbs in the gap (`is`, `does`, `can`, `do`, `are`), or skip the
heuristic when the conversation already has assistant turns about the corpus, and let the LLM
classifier (which sees `previous`) decide.

## T1 fix (working tree, 2026-10-06)

| # | Status | How verified |
|---|---|---|
| T1 | Fixed | The first `_ABOUT_ASSISTANT` alternative no longer accepts arbitrary text before "this/you/your <system/app/tool/...>"; only a linking verb is allowed (`what is`, `what's`, `how does`, ...), and `who` was removed from that alternative. Regression test `test_follow_ups_about_real_equipment_are_not_assistant_questions` checks that "Who owns this tool?", "Who maintains this tool?", "How reliable is this tool?", "What's the status of this tool?" and "How old is this system?" return `False`, while "what's this app for?", "How does this system work?" and "what is this tool?" still return `True`. The earlier tests for #1 and N1 still pass. |
| #1 | Fixed | With T1 closed, every question reported under #1, N1 and T1 reaches retrieval. |

## Not a code bug, but worth confirming
- ~~The working tree modifies or renames files under `data/`: the meeting transcripts were re-dated
  from 2024 to 2026 and every Office file changed. CLAUDE.md says `data/` is read-only. `golden.jsonl`
  was updated to match, so this looks deliberate, but please confirm.~~
  Resolved: the user approved these changes on 2026-10-06 (quality pass and 104-week date shift),
  and CLAUDE.md's Dataset section records them.
- ~~`backend/app/ingest.py:412` still has a stale comment, `# CLI: uv run python -m app.ingestion`.~~
  Fixed: it now reads `app.ingest`.
