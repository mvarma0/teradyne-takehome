"""SQLite: connection and schema, plus every repository (documents, chat, routing and gaps)."""

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.schemas import EnrichmentResult, SourceDoc

# ---- sqlite -------------------------------------------------------------------------------
# SQLite connection helper. One short-lived connection per unit of work (thread-safe).

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = get_settings().sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_ADDED_COLUMNS = {
    "documents": {"extra_json": "TEXT NOT NULL DEFAULT '{}'", "content": "TEXT"},
}


def init_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA_PATH.read_text())
        for table, columns in _ADDED_COLUMNS.items():
            existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


# ---- repository ---------------------------------------------------------------------------
# Structured document store (SQLite).

_JSON_FIELDS = {
    "authors_json": "authors",
    "attendees_json": "attendees",
    "products_json": "products",
    "key_topics_json": "key_topics",
    "decisions_json": "decisions",
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _decode(row: dict, action_items: list[dict]) -> dict:
    skip = {"enrichment_json", "extra_json", "content"}
    out = {k: v for k, v in row.items() if k not in _JSON_FIELDS and k not in skip}
    extra = json.loads(row.get("extra_json") or "{}")
    out["meeting_type"] = extra.get("meeting_type")
    out["location"] = extra.get("location")
    out["attendee_roles"] = extra.get("attendee_roles", {})
    out["author_roles"] = extra.get("author_roles", {})
    out["reviewers"] = extra.get("reviewers", [])
    out["format"] = extra.get("format")
    out["pages"] = extra.get("pages")
    out["rules_applied"] = extra.get("rules_applied", [])
    for col, key in _JSON_FIELDS.items():
        out[key] = json.loads(row[col] or "[]")
    out["doc_id"] = out.pop("id")
    out["action_items"] = [
        {"owner": a["owner"], "task": a["task"], "due_date": a["due_date"]} for a in action_items
    ]
    return out


def _action_items_for(conn, doc_ids: list[str]) -> dict[str, list[dict]]:
    if not doc_ids:
        return {}
    marks = ",".join("?" * len(doc_ids))
    rows = conn.execute(
        f"SELECT * FROM action_items WHERE document_id IN ({marks}) ORDER BY id", doc_ids
    ).fetchall()
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        grouped.setdefault(r["document_id"], []).append(r)
    return grouped


def upsert_document(
    src: SourceDoc, enrichment: EnrichmentResult, collection: str, n_chunks: int
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO documents (id, source_file, source_type, title, date, authors_json,
                attendees_json, attendees_source, content_hash, collection, topic_domain, priority,
                products_json, key_topics_json, summary, decisions_json, enrichment_json,
                extra_json, content, n_chunks, ingested_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                source_file=excluded.source_file, source_type=excluded.source_type,
                title=excluded.title, date=excluded.date, authors_json=excluded.authors_json,
                attendees_json=excluded.attendees_json,
                attendees_source=excluded.attendees_source, content_hash=excluded.content_hash,
                collection=excluded.collection, topic_domain=excluded.topic_domain,
                priority=excluded.priority, products_json=excluded.products_json,
                key_topics_json=excluded.key_topics_json, summary=excluded.summary,
                decisions_json=excluded.decisions_json, enrichment_json=excluded.enrichment_json,
                extra_json=excluded.extra_json, content=excluded.content,
                n_chunks=excluded.n_chunks, ingested_at=excluded.ingested_at
            """,
            (
                src.doc_id,
                src.source_file,
                src.source_type,
                src.title,
                src.date,
                json.dumps(src.authors),
                json.dumps(src.attendees),
                src.attendees_source,
                src.content_hash,
                collection,
                enrichment.topic_domain,
                enrichment.priority,
                json.dumps(enrichment.products),
                json.dumps(enrichment.key_topics),
                enrichment.summary,
                json.dumps(enrichment.decisions),
                enrichment.model_dump_json(),
                json.dumps(src.extra),
                src.content,
                n_chunks,
                _now(),
            ),
        )
        conn.execute("DELETE FROM action_items WHERE document_id = ?", (src.doc_id,))
        conn.executemany(
            "INSERT INTO action_items (document_id, owner, task, due_date) VALUES (?,?,?,?)",
            [(src.doc_id, a.owner, a.task, a.due_date) for a in enrichment.action_items],
        )


def get_document_state(doc_id: str) -> dict | None:
    """Minimal row used by ingestion to decide whether a file changed."""
    with connect() as conn:
        return conn.execute(
            "SELECT id, content_hash, collection FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()


def get_documents(doc_ids: list[str]) -> dict[str, dict]:
    if not doc_ids:
        return {}
    with connect() as conn:
        marks = ",".join("?" * len(doc_ids))
        rows = conn.execute(f"SELECT * FROM documents WHERE id IN ({marks})", doc_ids).fetchall()
        items = _action_items_for(conn, [r["id"] for r in rows])
        return {r["id"]: _decode(r, items.get(r["id"], [])) for r in rows}


def _filter_sql(
    topic_domain: str | None = None,
    priority: str | None = None,
    source_type: str | None = None,
    person: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[str, list]:
    clauses, params = [], []
    for col, val in (
        ("topic_domain", topic_domain),
        ("priority", priority),
        ("source_type", source_type),
    ):
        if val:
            clauses.append(f"{col} = ?")
            params.append(val)
    if person:
        clauses.append("(lower(attendees_json) LIKE ? OR lower(authors_json) LIKE ?)")
        params += [f"%{person.lower()}%"] * 2
    # Undated documents never match a date range.
    if date_from:
        clauses.append("date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        params.append(date_to)
    return (f"WHERE {' AND '.join(clauses)}" if clauses else ""), params


def find_doc_ids(**filters: str | None) -> set[str]:
    """Doc ids matching document-level filters (used to pre-filter retrieval)."""
    where, params = _filter_sql(**filters)
    with connect() as conn:
        return {r["id"] for r in conn.execute(f"SELECT id FROM documents {where}", params)}


def list_documents(
    topic_domain: str | None = None,
    priority: str | None = None,
    source_type: str | None = None,
    person: str | None = None,
) -> list[dict]:
    where, params = _filter_sql(topic_domain, priority, source_type, person)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM documents {where} ORDER BY date, source_file", params
        ).fetchall()
        items = _action_items_for(conn, [r["id"] for r in rows])
        return [_decode(r, items.get(r["id"], [])) for r in rows]


def list_all_doc_ids() -> list[str]:
    with connect() as conn:
        return [r["id"] for r in conn.execute("SELECT id FROM documents")]


def delete_document(doc_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


def get_document_content(doc_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT content FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return row["content"] if row else None


def count_documents() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]


def get_cached_enrichment(content_hash: str, model: str) -> EnrichmentResult | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT enrichment_json FROM enrichment_cache WHERE content_hash = ? AND model = ?",
            (content_hash, model),
        ).fetchone()
    return EnrichmentResult.model_validate_json(row["enrichment_json"]) if row else None


def cache_enrichment(content_hash: str, model: str, result: EnrichmentResult) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO enrichment_cache VALUES (?,?,?,?)",
            (content_hash, model, result.model_dump_json(), _now()),
        )


# ---- chat repo ----------------------------------------------------------------------------
# Conversations and messages. Every answered query is an assistant message (id = query id).


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


def _decode_message(row: dict) -> dict:
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
    return _decode_message(row) if row else None


def list_messages(conv_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at", (conv_id,)
        ).fetchall()
    return [_decode_message(r) for r in rows]


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


# ---- feedback repo ------------------------------------------------------------------------
# Routing suggestions, gaps (low confidence / rejections / corrections) and the review queue.


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


def gaps_for_message(message_id: str) -> list[dict]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM gaps WHERE message_id = ? ORDER BY created_at", (message_id,)
        ).fetchall()
