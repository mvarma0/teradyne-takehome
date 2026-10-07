"""HTTP API: health, documents, ingestion, chat, query, traces, feedback, routing, review
queue, metrics and evals."""

import json
import logging
import re

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse

from app import db, evals, feedback, metrics
from app.answer import ChatRequest, answer, citation_payload, run_chat
from app.config import get_settings
from app.evals import synthesize
from app.ingest import run_ingestion
from app.llm import ConfigError, collection_name, is_rate_limited, rate_limited_detail
from app.loaders import OFFICE_TYPES
from app.schemas import (
    ChatBody,
    CorrectBody,
    DocumentMetadata,
    EvalRunBody,
    FeedbackBody,
    IngestRequest,
    QueryRequest,
    RejectBody,
    RenameBody,
    ReviewBody,
    SendRoutingBody,
    SynthesizeBody,
)
from app.search import count_chunks, doc_chunks, retrieve

# ---- routes -------------------------------------------------------------------------------
# Core routes: health, stats, ingestion, documents.

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/stats")
def stats() -> dict:
    s = get_settings()
    docs = db.list_documents()
    by_type: dict[str, int] = {}
    for d in docs:
        by_type[d["source_type"]] = by_type.get(d["source_type"], 0) + 1
    return {
        "documents": len(docs),
        "by_type": by_type,
        "chunks": count_chunks(),
        "collection": collection_name(),
        "llm": f"{s.llm_provider}:{s.llm_model}",
        "embeddings": f"{s.embedding_provider}:{s.embedding_model}",
        "reranker": s.reranker,
        "confidence_threshold": s.confidence_threshold,
        "data_dir": str(s.data_dir),
    }


# Sync handlers run in FastAPI's threadpool, so long model calls don't block the event loop.
@router.post("/ingest")
def ingest(req: IngestRequest | None = None) -> dict:
    try:
        return run_ingestion(force=bool(req and req.force)).to_dict()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.post("/documents/upload")
async def upload_document(request: Request, filename: str = Query(...)) -> dict:
    """Save a new or updated source into data/ (same name replaces it), then ingest changes.

    The request body is the raw file. Meetings (.md) go to data/meetings/, Office files to
    data/documents/<ext>/, which is where ingestion discovers them.
    """
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", filename.replace("\\", "/").rsplit("/", 1)[-1])
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix:  # ingestion discovers lower-case extensions (*.md, *.docx, ...)
        name = name[: -len(suffix)] + suffix
    if not name.strip(" .") or name.startswith(("~$", ".")):
        raise HTTPException(status_code=400, detail="invalid file name")
    s = get_settings()
    if suffix == ".md":
        folder = s.meetings_dir
    elif suffix in OFFICE_TYPES:
        folder = s.documents_dir / suffix[1:]
    else:
        allowed = ", ".join([".md", *sorted(OFFICE_TYPES)])
        raise HTTPException(status_code=415, detail=f"unsupported file type; allowed: {allowed}")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty file")
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file larger than 25 MB")
    path = folder / name
    replaced = path.exists()
    folder.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    try:
        report = (await run_in_threadpool(run_ingestion)).to_dict()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=f"saved, but {exc}; ingest later") from exc
    return {
        "source_file": path.relative_to(s.data_dir).as_posix(),
        "replaced": replaced,
        "report": report,
    }


@router.get("/documents", response_model=list[DocumentMetadata])
def list_documents(
    topic_domain: str | None = None,
    priority: str | None = None,
    source_type: str | None = None,
    person: str | None = Query(None, description="attendee/author substring"),
) -> list[dict]:
    return db.list_documents(topic_domain, priority, source_type, person)


def _document_or_404(doc_id: str) -> dict:
    doc = db.get_documents([doc_id]).get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    return doc


@router.get("/documents/{doc_id}", response_model=DocumentMetadata)
def get_document(doc_id: str) -> dict:
    return _document_or_404(doc_id)


@router.get("/documents/{doc_id}/content")
def get_document_content(doc_id: str) -> dict:
    """Metadata + normalized content + chunks (for the viewer to highlight citations)."""
    doc = _document_or_404(doc_id)
    return {
        "document": doc,
        "content": db.get_document_content(doc_id),
        "chunks": doc_chunks(doc_id),
    }


@router.get("/documents/{doc_id}/file")
def download_document(doc_id: str) -> FileResponse:
    doc = _document_or_404(doc_id)
    data_dir = get_settings().data_dir.resolve()
    path = (data_dir / doc["source_file"]).resolve()
    if data_dir not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="source file not available")
    return FileResponse(path, filename=path.name)


# ---- routes chat --------------------------------------------------------------------------
# Chat (SSE streaming), single-shot query, conversations and answer feedback.

log = logging.getLogger(__name__)


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
            detail = (
                rate_limited_detail() if is_rate_limited(exc) else f"{type(exc).__name__}: {exc}"
            )
            yield _sse("error", {"detail": detail})

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
        docs = db.get_documents(doc_ids)
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
    msg = db.get_message(query_id)
    if not msg or msg["role"] != "assistant":
        raise HTTPException(status_code=404, detail="query not found")
    payload = msg["payload"] or {}
    payload["routing"] = db.routing_for_message(query_id) or payload.get("routing", [])
    return {**payload, "status": msg["status"], "feedback": msg["feedback"]}


@router.get("/traces")
def list_traces(limit: int = 200) -> list[dict]:
    """Every answered question, newest first, with what it retrieved and cited."""
    return db.list_traces(limit)


@router.get("/traces/{query_id}")
def get_trace(query_id: str) -> dict:
    """Full lineage of one answer: question -> guardrail -> rewrite -> retrieval -> claims ->
    confidence -> status, routing, gaps and feedback."""
    msg = db.get_message(query_id)
    if not msg or msg["role"] != "assistant":
        raise HTTPException(status_code=404, detail="query not found")
    payload = msg.pop("payload") or {}
    payload["routing"] = db.routing_for_message(query_id) or payload.get("routing", [])
    return {
        **payload,
        **msg,
        "query": msg["query_text"],
        "gaps": db.gaps_for_message(query_id),
    }


def _not_found(exc: feedback.NotFound) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.post("/query/{query_id}/correct")
def correct(query_id: str, body: CorrectBody) -> dict:
    try:
        return feedback.correct(query_id, body.correction, body.submitted_by)
    except feedback.NotFound as exc:
        raise _not_found(exc) from exc


@router.post("/query/{query_id}/reject")
def reject(query_id: str, body: RejectBody | None = None) -> dict:
    body = body or RejectBody()
    try:
        return feedback.reject(query_id, body.reason, body.submitted_by)
    except feedback.NotFound as exc:
        raise _not_found(exc) from exc


@router.post("/query/{query_id}/feedback")
def rate_answer(query_id: str, body: FeedbackBody) -> dict:
    try:
        feedback.rate(query_id, body.rating)
    except feedback.NotFound as exc:
        raise _not_found(exc) from exc
    return {"query_id": query_id, "feedback": body.rating}


@router.get("/conversations")
def list_conversations() -> list[dict]:
    return db.list_conversations()


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str) -> dict:
    conv = db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    messages = db.list_messages(conv_id)
    for m in messages:
        if m["role"] == "assistant" and m["payload"]:
            m["payload"]["routing"] = db.routing_for_message(m["id"]) or m["payload"].get(
                "routing", []
            )
    return {**conv, "messages": messages}


@router.patch("/conversations/{conv_id}")
def rename_conversation(conv_id: str, body: RenameBody) -> dict:
    if not db.get_conversation(conv_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    db.rename_conversation(conv_id, body.title)
    return db.get_conversation(conv_id)


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str) -> None:
    db.delete_conversation(conv_id)


# ---- routes review ------------------------------------------------------------------------
# Gaps, corrections, review queue, routing actions, monitoring metrics and evals.


@router.get("/gaps")
def list_gaps(type: str | None = None, status: str | None = None) -> list[dict]:  # noqa: A002
    return db.list_gaps(type, status)


@router.get("/gaps/{gap_id}")
def get_gap(gap_id: str) -> dict:
    gap = db.get_gap(gap_id)
    if not gap:
        raise HTTPException(status_code=404, detail="gap not found")
    return gap


@router.get("/review-queue")
def review_queue(status: str | None = None, type: str | None = None) -> dict:  # noqa: A002
    return {"counts": db.gap_counts(), "items": db.list_gaps(type, status)}


@router.patch("/review-queue/{gap_id}")
def review(gap_id: str, body: ReviewBody) -> dict:
    gap = db.review_gap(gap_id, body.review_status, body.reviewer_note)
    if not gap:
        raise HTTPException(status_code=404, detail="gap not found")
    return gap


@router.post("/routing/{routing_id}/send")
def send_routing(routing_id: str, body: SendRoutingBody) -> dict:
    """Records the (edited) question as sent. Delivery is intentionally log-only."""
    if not db.get_routing(routing_id):
        raise HTTPException(status_code=404, detail="routing suggestion not found")
    db.mark_routing_sent(routing_id, body.question, body.sent_by)
    return db.get_routing(routing_id)


@router.post("/routing/{routing_id}/dismiss")
def dismiss_routing(routing_id: str) -> dict:
    if not db.get_routing(routing_id):
        raise HTTPException(status_code=404, detail="routing suggestion not found")
    db.dismiss_routing(routing_id)
    return db.get_routing(routing_id)


@router.get("/metrics")
def get_metrics(window: str = "24h") -> dict:
    if window not in metrics.WINDOWS:
        raise HTTPException(
            status_code=400, detail=f"window must be one of {list(metrics.WINDOWS)}"
        )
    return metrics.summary(window)


@router.get("/evals")
def list_evals() -> dict:
    return {"datasets": evals.dataset_info(), "runs": evals.list_runs()}


@router.post("/evals/run", status_code=202)
def run_eval(body: EvalRunBody | None = None) -> dict:
    dataset = (body or EvalRunBody()).dataset
    try:
        return {"run_id": evals.start_background(dataset), "dataset": dataset}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/evals/{run_id}")
def get_eval(run_id: str) -> dict:
    run = evals.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="eval run not found")
    return run


@router.post("/evals/synthesize")
def synthesize_cases(body: SynthesizeBody | None = None) -> dict:
    return {"generated": synthesize((body or SynthesizeBody()).n)}
