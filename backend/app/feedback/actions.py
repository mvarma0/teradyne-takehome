"""Consumer feedback on answers: corrections, rejections (-> routing), thumbs up/down."""

from langchain_core.documents import Document

from app.db import chat_repo, feedback_repo, repository
from app.retrieval.types import RetrievedChunk
from app.routing.router import suggest_routing


class NotFound(LookupError):
    pass


def _assistant_message(message_id: str) -> dict:
    msg = chat_repo.get_message(message_id)
    if not msg or msg["role"] != "assistant":
        raise NotFound(f"answer {message_id} not found")
    return msg


def _chunks_from_payload(payload: dict) -> list[RetrievedChunk]:
    chunks = []
    for c in payload.get("citations", []):
        meta = {"doc_id": c["doc_id"], "chunk_id": c["chunk_id"], "source_file": c["source_file"]}
        doc = Document(page_content=f"[{c['title']}]\n{c['snippet']}", metadata=meta)
        chunks.append(
            RetrievedChunk(
                document=doc,
                rerank_score=c["scores"].get("rerank"),
                semantic_score=c["scores"].get("semantic"),
            )
        )
    return chunks


def correct(message_id: str, correction: str, submitted_by: str | None) -> dict:
    msg = _assistant_message(message_id)
    gap = feedback_repo.create_gap(
        message_id,
        "correction",
        msg["query_text"],
        msg["content"],
        correction_text=correction,
        submitted_by=submitted_by,
    )
    chat_repo.update_message(message_id, status="corrected")
    return gap


def reject(message_id: str, reason: str | None, submitted_by: str | None) -> dict:
    """Capture the rejection and return routing (reusing existing suggestions if any)."""
    msg = _assistant_message(message_id)
    gap = feedback_repo.create_gap(
        message_id,
        "rejected",
        msg["query_text"],
        msg["content"],
        reason=reason,
        submitted_by=submitted_by,
    )
    chat_repo.update_message(message_id, status="rejected")
    routing = feedback_repo.routing_for_message(message_id)
    if not routing:
        payload = msg["payload"] or {}
        chunks = _chunks_from_payload(payload)
        docs = repository.get_documents(list({c.document.metadata["doc_id"] for c in chunks}))
        situation = f"The user rejected the knowledge base's answer. Reason: {reason or 'n/a'}."
        suggestions = suggest_routing(
            msg["standalone_query"] or msg["query_text"], chunks, docs, situation
        )
        routing = feedback_repo.save_routing(message_id, suggestions)
        payload["routing"] = routing
        chat_repo.update_message(message_id, payload=payload)
    return {**gap, "routing": routing}


def rate(message_id: str, rating: str | None) -> None:
    _assistant_message(message_id)
    chat_repo.update_message(message_id, feedback=rating)
