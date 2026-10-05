from fastapi import APIRouter, HTTPException, Query

from app.answer.service import run_query
from app.config import get_settings
from app.db import repository
from app.ingestion.pipeline import run_ingestion
from app.llm.factory import collection_name
from app.models.api import DocumentMetadata, IngestRequest, QueryRequest, QueryResponse
from app.retrieval.vectorstore import count_chunks

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/stats")
def stats() -> dict:
    s = get_settings()
    return {
        "documents": repository.count_documents(),
        "chunks": count_chunks(),
        "collection": collection_name(),
        "llm": f"{s.llm_provider}:{s.llm_model}",
        "embeddings": f"{s.embedding_provider}:{s.embedding_model}",
        "reranker": s.reranker,
        "data_dir": str(s.data_dir),
    }


# Sync handlers run in FastAPI's threadpool, so long model calls don't block the event loop.
@router.post("/ingest")
def ingest(req: IngestRequest | None = None) -> dict:
    try:
        return run_ingestion(force=bool(req and req.force)).to_dict()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    return run_query(req)


@router.get("/documents", response_model=list[DocumentMetadata])
def list_documents(
    topic_domain: str | None = None,
    priority: str | None = None,
    source_type: str | None = None,
    person: str | None = Query(None, description="attendee/author substring"),
) -> list[dict]:
    return repository.list_documents(topic_domain, priority, source_type, person)


@router.get("/documents/{doc_id}", response_model=DocumentMetadata)
def get_document(doc_id: str) -> dict:
    doc = repository.get_documents([doc_id]).get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    return doc
