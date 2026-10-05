#!/usr/bin/env bash
# Exercise 1 smoke test against a running server: ./scripts/smoke_ex1.sh [base_url]
set -euo pipefail
BASE="${1:-http://localhost:8000}"
pass() { echo "  ok  $1"; }
fail() { echo "  FAIL $1"; exit 1; }
post() {
  local body='{}'
  [ $# -ge 2 ] && body="$2"
  curl -sf -X POST "$BASE$1" -H 'content-type: application/json' -d "$body"
}

echo "== health"
[ "$(curl -sf "$BASE/api/health" | jq -r .status)" = "ok" ] && pass "health" || fail "health"

echo "== ingest (first run may take a while: enrichment + embeddings)"
REPORT=$(post /api/ingest)
echo "$REPORT" | jq -c '{files_found, ingested, skipped_unchanged, removed, chunks_written, failed, warnings}'
[ "$(echo "$REPORT" | jq '.files_found')" -gt 0 ] && pass "found meeting files" || fail "no files in data/meetings"
[ "$(echo "$REPORT" | jq '.failed | length')" -eq 0 ] && pass "no ingestion failures" || fail "ingestion failures"

echo "== stats"
curl -sf "$BASE/api/stats" | jq -c .

echo "== documents (derived metadata)"
DOCS=$(curl -sf "$BASE/api/documents")
N=$(echo "$DOCS" | jq length)
[ "$N" -gt 0 ] && pass "$N documents" || fail "no documents"
echo "$DOCS" | jq -r '.[] | "  \(.source_file) | \(.topic_domain) | \(.priority) | \(.attendees | join(", "))"'
[ "$(echo "$DOCS" | jq '[.[] | select(.topic_domain == null)] | length')" -eq 0 ] \
  && pass "every document has topic_domain" || fail "missing topic_domain"

echo "== query"
Q='{"query": "What is causing the Eagle-5 yield problems and who is working on it?"}'
RESP=$(post /api/query "$Q")
echo "$RESP" | jq '{answer, retrieval}'
echo "$RESP" | jq -r '.results[] | "  #\(.rank) \(.source_file) [\(.section)] topic=\(.topic_domain) prio=\(.priority) rerank=\(.scores.rerank)"'
[ "$(echo "$RESP" | jq '.results | length')" -gt 0 ] && pass "results returned" || fail "no results"
[ "$(echo "$RESP" | jq '[.results[] | select((.attendees | length) == 0)] | length')" -eq 0 ] \
  && pass "results carry attendees" || fail "result without attendees"
[ "$(echo "$RESP" | jq '.documents | length')" -gt 0 ] && pass "derived metadata attached" || fail "no document metadata"

echo "== filtered query"
F='{"query": "action items", "filters": {"topic_domain": "yield"}, "generate_answer": false}'
post /api/query "$F" | jq -e '[.results[] | select(.topic_domain != "yield")] | length == 0' >/dev/null \
  && pass "topic filter respected" || fail "topic filter leaked"

echo "ALL CHECKS PASSED"
