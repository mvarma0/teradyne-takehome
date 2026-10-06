"""Conversations and messages. Every answered query is an assistant message (id = query id)."""

import json
import uuid
from datetime import UTC, datetime

from app.db.sqlite import connect


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def create_conversation(title: str) -> dict:
    conv = {"id": new_id(), "title": title[:80] or "New chat", "created_at": now()}
    conv["updated_at"] = conv["created_at"]
    with connect() as conn:
        conn.execute(
            "INSERT INTO conversations VALUES (:id, :title, :created_at, :updated_at)", conv
        )
    return conv


def get_conversation(conv_id: str) -> dict | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()


def list_conversations(limit: int = 100) -> list[dict]:
    with connect() as conn:
        return conn.execute(
            """SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id)
               AS n_messages FROM conversations c ORDER BY updated_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()


def rename_conversation(conv_id: str, title: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title[:80], now(), conv_id),
        )


def delete_conversation(conv_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))


def _decode(row: dict) -> dict:
    out = dict(row)
    out["payload"] = json.loads(out.pop("payload_json") or "null")
    out["filters"] = json.loads(out.pop("filters_json") or "null")
    out["confident"] = None if out["confident"] is None else bool(out["confident"])
    return out


def add_user_message(conv_id: str, content: str) -> dict:
    msg = {
        "id": new_id(),
        "conversation_id": conv_id,
        "role": "user",
        "content": content,
        "created_at": now(),
    }
    with connect() as conn:
        conn.execute(
            """INSERT INTO messages (id, conversation_id, role, content, created_at)
               VALUES (:id, :conversation_id, :role, :content, :created_at)""",
            msg,
        )
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now(), conv_id))
    return msg


def add_assistant_message(
    msg_id: str,
    conv_id: str | None,
    content: str,
    query_text: str,
    standalone_query: str,
    filters: dict | None,
    payload: dict,
    confidence: float | None,
    confident: bool | None,
    status: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO messages (id, conversation_id, role, content, query_text,
                   standalone_query, filters_json, payload_json, confidence, confident, status,
                   created_at)
               VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg_id,
                conv_id,
                content,
                query_text,
                standalone_query,
                json.dumps(filters),
                json.dumps(payload),
                confidence,
                None if confident is None else int(confident),
                status,
                now(),
            ),
        )
        if conv_id:
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now(), conv_id))


def get_message(msg_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
    return _decode(row) if row else None


def list_messages(conv_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at", (conv_id,)
        ).fetchall()
    return [_decode(r) for r in rows]


def recent_history(conv_id: str, max_messages: int) -> list[dict]:
    """Last N messages (oldest first) as {role, content} for prompting."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT role, content FROM messages WHERE conversation_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (conv_id, max_messages),
        ).fetchall()
    return list(reversed(rows))


def update_message(msg_id: str, **fields) -> None:
    if "payload" in fields:
        fields["payload_json"] = json.dumps(fields.pop("payload"))
    sets = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE messages SET {sets} WHERE id = ?", [*fields.values(), msg_id])


def list_traces(limit: int = 200) -> list[dict]:
    """Assistant messages newest first, summarised for the traceability list."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT m.id, m.conversation_id, m.query_text, m.standalone_query, m.status,
                   m.confidence, m.feedback, m.created_at, m.payload_json,
                   (SELECT COUNT(*) FROM gaps g WHERE g.message_id = m.id) AS n_gaps
               FROM messages m WHERE m.role = 'assistant' ORDER BY m.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        payload = json.loads(r.pop("payload_json") or "{}")
        cited = set(payload.get("cited") or [])
        citations = payload.get("citations") or []
        r["n_retrieved"] = len(citations)
        r["n_cited"] = len(cited)
        r["cited_files"] = list(
            dict.fromkeys(c["source_file"] for c in citations if c.get("n") in cited)
        )
        r["guardrail"] = (payload.get("guardrails") or {}).get("category")
        r["latency_ms"] = payload.get("latency_ms")
        out.append(r)
    return out
