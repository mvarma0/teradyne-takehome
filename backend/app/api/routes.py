"""Core routes: health, stats, ingestion, documents."""

import re

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.config import get_settings
from app.db import repository
from app.ingestion.loaders.office import OFFICE_TYPES
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


MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.post("/documents/upload")
async def upload_document(request: Request, filename: str = Query(...)) -> dict:
    """Save a new or updated source into data/ (same name replaces it), then ingest changes.

    The request body is the raw file. Meetings (.md) go to data/meetings/, Office files to
    data/documents/<ext>/, which is where ingestion discovers them.
    """
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", filename.replace("\\", "/").rsplit("/", 1)[-1])
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
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
