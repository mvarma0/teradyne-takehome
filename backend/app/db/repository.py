"""Structured document store (SQLite)."""

import json
from datetime import UTC, datetime

from app.db.sqlite import connect
from app.models.enrichment import EnrichmentResult
from app.models.source import SourceDoc

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
    skip = {"enrichment_json", "extra_json"}
    out = {k: v for k, v in row.items() if k not in _JSON_FIELDS and k not in skip}
    extra = json.loads(row.get("extra_json") or "{}")
    out["meeting_type"] = extra.get("meeting_type")
    out["location"] = extra.get("location")
    out["attendee_roles"] = extra.get("attendee_roles", {})
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
                extra_json, n_chunks, ingested_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                source_file=excluded.source_file, source_type=excluded.source_type,
                title=excluded.title, date=excluded.date, authors_json=excluded.authors_json,
                attendees_json=excluded.attendees_json,
                attendees_source=excluded.attendees_source, content_hash=excluded.content_hash,
                collection=excluded.collection, topic_domain=excluded.topic_domain,
                priority=excluded.priority, products_json=excluded.products_json,
                key_topics_json=excluded.key_topics_json, summary=excluded.summary,
                decisions_json=excluded.decisions_json, enrichment_json=excluded.enrichment_json,
                extra_json=excluded.extra_json,
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


def list_documents(
    topic_domain: str | None = None,
    priority: str | None = None,
    source_type: str | None = None,
    person: str | None = None,
) -> list[dict]:
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
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM documents {where} ORDER BY date, source_file", params
        ).fetchall()
        items = _action_items_for(conn, [r["id"] for r in rows])
        return [_decode(r, items.get(r["id"], [])) for r in rows]


def list_doc_ids(source_type: str) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id FROM documents WHERE source_type = ?", (source_type,)
        ).fetchall()
        return [r["id"] for r in rows]


def delete_document(doc_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


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
