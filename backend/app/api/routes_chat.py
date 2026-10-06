"""Chat (SSE streaming), single-shot query, conversations and answer feedback."""

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.answer.chat import ChatRequest, answer, citation_payload, run_chat
from app.db import chat_repo, feedback_repo, repository
from app.feedback import actions
from app.llm.factory import ConfigError
from app.models.api import (
    ChatBody,
    CorrectBody,
    FeedbackBody,
    QueryRequest,
    RejectBody,
    RenameBody,
)
from app.retrieval.hybrid import retrieve

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/chat/stream")
def chat_stream(body: ChatBody) -> StreamingResponse:
    """Server-Sent Events: conversation, status, guardrail, sources, token*, final | error."""
    req = ChatRequest(
        message=body.message,
        conversation_id=body.conversation_id,
        filters=body.filters,
        top_k=body.top_k,
        rerank=body.rerank,
    )

    def events():
        try:
            for ev in run_chat(req):
                yield _sse(ev["event"], ev["data"])
        except ConfigError as exc:
            yield _sse("error", {"detail": str(exc)})
        except Exception as exc:
            log.exception("chat stream failed")
            yield _sse("error", {"detail": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/query")
def query(req: QueryRequest) -> dict:
    """Single-shot NL query (no conversation). Same payload as the chat 'final' event."""
    if not req.generate_answer:
        result = retrieve(req.query, req.filters, req.top_k, req.rerank)
        citations = [citation_payload(i, c) for i, c in enumerate(result.chunks, start=1)]
        doc_ids = list(dict.fromkeys(c["doc_id"] for c in citations))
        docs = repository.get_documents(doc_ids)
        return {
            "query": req.query,
            "answer": None,
            "citations": citations,
            "documents": [docs[d] for d in doc_ids if d in docs],
        }
    return answer(
        ChatRequest(
            message=req.query, filters=req.filters, top_k=req.top_k, rerank=req.rerank, chat=False
        )
    )


@router.get("/query/{query_id}")
def get_query(query_id: str) -> dict:
    msg = chat_repo.get_message(query_id)
    if not msg or msg["role"] != "assistant":
        raise HTTPException(status_code=404, detail="query not found")
    payload = msg["payload"] or {}
    payload["routing"] = feedback_repo.routing_for_message(query_id) or payload.get("routing", [])
    return {**payload, "status": msg["status"], "feedback": msg["feedback"]}


@router.get("/traces")
def list_traces(limit: int = 200) -> list[dict]:
    """Every answered question, newest first, with what it retrieved and cited."""
    return chat_repo.list_traces(limit)


@router.get("/traces/{query_id}")
def get_trace(query_id: str) -> dict:
    """Full lineage of one answer: question -> guardrail -> rewrite -> retrieval -> claims ->
    confidence -> status, routing, gaps and feedback."""
    msg = chat_repo.get_message(query_id)
    if not msg or msg["role"] != "assistant":
        raise HTTPException(status_code=404, detail="query not found")
    payload = msg.pop("payload") or {}
    payload["routing"] = feedback_repo.routing_for_message(query_id) or payload.get("routing", [])
    return {
        **payload,
        **msg,
        "query": msg["query_text"],
        "gaps": feedback_repo.gaps_for_message(query_id),
    }


def _not_found(exc: actions.NotFound) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.post("/query/{query_id}/correct")
def correct(query_id: str, body: CorrectBody) -> dict:
    try:
        return actions.correct(query_id, body.correction, body.submitted_by)
    except actions.NotFound as exc:
        raise _not_found(exc) from exc


@router.post("/query/{query_id}/reject")
def reject(query_id: str, body: RejectBody | None = None) -> dict:
    body = body or RejectBody()
    try:
        return actions.reject(query_id, body.reason, body.submitted_by)
    except actions.NotFound as exc:
        raise _not_found(exc) from exc


@router.post("/query/{query_id}/feedback")
def feedback(query_id: str, body: FeedbackBody) -> dict:
    try:
        actions.rate(query_id, body.rating)
    except actions.NotFound as exc:
        raise _not_found(exc) from exc
    return {"query_id": query_id, "feedback": body.rating}


@router.get("/conversations")
def list_conversations() -> list[dict]:
    return chat_repo.list_conversations()


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str) -> dict:
    conv = chat_repo.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    messages = chat_repo.list_messages(conv_id)
    for m in messages:
        if m["role"] == "assistant" and m["payload"]:
            m["payload"]["routing"] = feedback_repo.routing_for_message(m["id"]) or m[
                "payload"
            ].get("routing", [])
    return {**conv, "messages": messages}


@router.patch("/conversations/{conv_id}")
def rename_conversation(conv_id: str, body: RenameBody) -> dict:
    if not chat_repo.get_conversation(conv_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    chat_repo.rename_conversation(conv_id, body.title)
    return chat_repo.get_conversation(conv_id)


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str) -> None:
    chat_repo.delete_conversation(conv_id)
