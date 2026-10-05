"""Routing suggestions, gaps (low confidence / rejections / corrections) and the review queue."""

import json

from app.db.chat_repo import new_id, now
from app.db.sqlite import connect


# ---- routing ------------------------------------------------------------------------------
def save_routing(message_id: str, suggestions: list[dict]) -> list[dict]:
    saved = []
    with connect() as conn:
        for s in suggestions:
            row = {
                "id": new_id(),
                "message_id": message_id,
                "person": s["person"],
                "role": s.get("role"),
                "reason": s["reason"],
                "matched_sources_json": json.dumps(s.get("matched_sources", [])),
                "draft_question": s["draft_question"],
                "created_at": now(),
            }
            conn.execute(
                """INSERT INTO routing_suggestions (id, message_id, person, role, reason,
                       matched_sources_json, draft_question, created_at)
                   VALUES (:id, :message_id, :person, :role, :reason, :matched_sources_json,
                       :draft_question, :created_at)""",
                row,
            )
            saved.append(
                _decode_routing(
                    {
                        **row,
                        "status": "suggested",
                        "edited_question": None,
                        "sent_by": None,
                        "sent_at": None,
                    }
                )
            )
    return saved


def _decode_routing(row: dict) -> dict:
    out = dict(row)
    out["matched_sources"] = json.loads(out.pop("matched_sources_json") or "[]")
    out["routing_id"] = out["id"]
    return out


def routing_for_message(message_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM routing_suggestions WHERE message_id = ? ORDER BY created_at",
            (message_id,),
        ).fetchall()
    return [_decode_routing(r) for r in rows]


def get_routing(routing_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM routing_suggestions WHERE id = ?", (routing_id,)
        ).fetchone()
    return _decode_routing(row) if row else None


def mark_routing_sent(routing_id: str, question: str, sent_by: str | None) -> None:
    with connect() as conn:
        conn.execute(
            """UPDATE routing_suggestions SET status = 'sent', edited_question = ?, sent_by = ?,
                   sent_at = ? WHERE id = ?""",
            (question, sent_by, now(), routing_id),
        )


def dismiss_routing(routing_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE routing_suggestions SET status = 'dismissed' WHERE id = ?", (routing_id,)
        )


# ---- gaps -----------------------------------------------------------------------------------
def create_gap(
    message_id: str | None,
    gap_type: str,
    query_text: str,
    original_answer: str | None,
    correction_text: str | None = None,
    reason: str | None = None,
    submitted_by: str | None = None,
) -> dict:
    gap = {
        "id": new_id(),
        "message_id": message_id,
        "type": gap_type,
        "query_text": query_text,
        "original_answer": original_answer,
        "correction_text": correction_text,
        "reason": reason,
        "submitted_by": submitted_by,
        "created_at": now(),
    }
    with connect() as conn:
        conn.execute(
            """INSERT INTO gaps (id, message_id, type, query_text, original_answer,
                   correction_text, reason, submitted_by, created_at)
               VALUES (:id, :message_id, :type, :query_text, :original_answer, :correction_text,
                   :reason, :submitted_by, :created_at)""",
            gap,
        )
    return get_gap(gap["id"])


def get_gap(gap_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM gaps WHERE id = ?", (gap_id,)).fetchone()
    return _with_context(row) if row else None


def _with_context(gap: dict) -> dict:
    out = dict(gap)
    out["routing"] = routing_for_message(gap["message_id"]) if gap["message_id"] else []
    with connect() as conn:
        msg = conn.execute(
            "SELECT conversation_id, confidence, payload_json FROM messages WHERE id = ?",
            (gap["message_id"],),
        ).fetchone()
    payload = json.loads(msg["payload_json"] or "{}") if msg else {}
    out["conversation_id"] = msg["conversation_id"] if msg else None
    out["confidence"] = msg["confidence"] if msg else None
    out["citations"] = payload.get("citations", [])
    return out


def list_gaps(
    gap_type: str | None = None, review_status: str | None = None, limit: int = 200
) -> list[dict]:
    clauses, params = [], []
    if gap_type:
        clauses.append("type = ?")
        params.append(gap_type)
    if review_status:
        clauses.append("review_status = ?")
        params.append(review_status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT * FROM gaps {where}
                ORDER BY CASE review_status WHEN 'pending' THEN 0 ELSE 1 END, created_at DESC
                LIMIT ?""",
            [*params, limit],
        ).fetchall()
    return [_with_context(r) for r in rows]


def review_gap(gap_id: str, review_status: str, reviewer_note: str | None) -> dict | None:
    with connect() as conn:
        conn.execute(
            "UPDATE gaps SET review_status = ?, reviewer_note = ?, reviewed_at = ? WHERE id = ?",
            (review_status, reviewer_note, now(), gap_id),
        )
    return get_gap(gap_id)


def gap_counts() -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT type, review_status, COUNT(*) AS n FROM gaps GROUP BY type, review_status"
        ).fetchall()
    counts: dict = {"pending": 0, "total": 0, "by_type": {}}
    for r in rows:
        counts["total"] += r["n"]
        counts["by_type"][r["type"]] = counts["by_type"].get(r["type"], 0) + r["n"]
        if r["review_status"] == "pending":
            counts["pending"] += r["n"]
    return counts
