"""Core routes: health, stats, ingestion, documents."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import get_settings
from app.db import repository
from app.ingestion.pipeline import run_ingestion
from app.llm.factory import collection_name
from app.models.api import DocumentMetadata, IngestRequest
from app.retrieval.vectorstore import count_chunks, doc_chunks

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/stats")
def stats() -> dict:
    s = get_settings()
    docs = repository.list_documents()
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


@router.get("/documents", response_model=list[DocumentMetadata])
def list_documents(
    topic_domain: str | None = None,
    priority: str | None = None,
    source_type: str | None = None,
    person: str | None = Query(None, description="attendee/author substring"),
) -> list[dict]:
    return repository.list_documents(topic_domain, priority, source_type, person)


def _document_or_404(doc_id: str) -> dict:
    doc = repository.get_documents([doc_id]).get(doc_id)
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
        "content": repository.get_document_content(doc_id),
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
