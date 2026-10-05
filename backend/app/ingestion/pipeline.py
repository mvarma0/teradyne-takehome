"""Ingestion: load -> enrich -> SQLite -> chunk -> Chroma. Idempotent per file content hash."""

import logging
import threading
import time
from dataclasses import asdict, dataclass, field

from app.config import get_settings
from app.db import repository
from app.ingestion.chunking import chunk_document
from app.ingestion.enrich import enrich
from app.ingestion.loaders.meeting import iter_meeting_files, load_meeting, make_doc_id
from app.llm.factory import collection_name
from app.retrieval.bm25 import invalidate_bm25
from app.retrieval.vectorstore import delete_doc_chunks, replace_doc_chunks

log = logging.getLogger(__name__)
_lock = threading.Lock()


@dataclass
class IngestReport:
    collection: str
    files_found: int = 0
    ingested: int = 0
    skipped_unchanged: int = 0
    removed: int = 0
    chunks_written: int = 0
    duration_s: float = 0.0
    ingested_files: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def run_ingestion(force: bool = False) -> IngestReport:
    if not _lock.acquire(blocking=False):
        raise RuntimeError("An ingestion run is already in progress")
    try:
        return _run(force)
    finally:
        _lock.release()


def _run(force: bool) -> IngestReport:
    s = get_settings()
    started = time.perf_counter()
    report = IngestReport(collection=collection_name())

    files = iter_meeting_files(s.meetings_dir)
    report.files_found = len(files)
    if not s.meetings_dir.is_dir():
        report.warnings.append(f"Meetings folder not found: {s.meetings_dir}")
    elif not files:
        report.warnings.append(f"No .md files in {s.meetings_dir}")

    seen: set[str] = set()
    for path in files:
        rel = path.relative_to(s.data_dir).as_posix()
        doc_id = make_doc_id(rel)
        seen.add(doc_id)
        try:
            src = load_meeting(path, s.data_dir)
            state = repository.get_document_state(doc_id)
            unchanged = (
                state
                and state["content_hash"] == src.content_hash
                and state["collection"] == report.collection
            )
            if unchanged and not force:
                report.skipped_unchanged += 1
                continue
            enrichment = enrich(src, force=force)
            chunks = chunk_document(src, enrichment)
            replace_doc_chunks(doc_id, chunks)
            repository.upsert_document(src, enrichment, report.collection, len(chunks))
            report.ingested += 1
            report.chunks_written += len(chunks)
            report.ingested_files.append(rel)
            if src.attendees_source in ("speakers", "none"):
                report.warnings.append(
                    f"{rel}: no attendee list found (attendees from {src.attendees_source})"
                )
        except Exception as exc:  # keep going; report per-file failures
            log.exception("failed to ingest %s", rel)
            report.failed.append({"file": rel, "error": f"{type(exc).__name__}: {exc}"})

    # Prune documents whose source file no longer exists.
    for stale in set(repository.list_doc_ids("meeting")) - seen:
        delete_doc_chunks(stale)
        repository.delete_document(stale)
        report.removed += 1

    invalidate_bm25()
    report.duration_s = round(time.perf_counter() - started, 2)
    log.info("ingestion finished: %s", report)
    return report
