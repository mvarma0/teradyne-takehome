"""End-to-end against local Ollama (qwen2.5:7b + nomic-embed-text) with docling enabled."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.state import reset_all
from tests.conftest import requires_ollama

pytestmark = [requires_ollama, pytest.mark.integration]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("USE_DOCLING", "true")
    reset_all()
    with TestClient(app) as c:
        yield c


def test_ingest_query_documents_flow(client, isolated_env):
    # Query before ingestion degrades gracefully.
    empty = client.post("/api/query", json={"query": "anything"}).json()
    assert empty["results"] == []

    report = client.post("/api/ingest").json()
    assert report["files_found"] == 3 and report["ingested"] == 3, report
    assert report["failed"] == [] and report["chunks_written"] >= 3

    # Idempotent re-run.
    again = client.post("/api/ingest").json()
    assert again["ingested"] == 0 and again["skipped_unchanged"] == 3

    docs = client.get("/api/documents").json()
    assert len(docs) == 3
    eagle = next(d for d in docs if d["source_file"].endswith("meeting_01_eagle5_yield.md"))
    assert eagle["attendees"] == ["Sarah Chen", "Marcus Rivera", "Tom Bradley", "Jennifer Liu"]
    assert eagle["topic_domain"] in {"yield", "quality_compliance"}
    assert "Eagle-5" in eagle["products"]
    assert eagle["action_items"], "enrichment should extract action items"

    resp = client.post("/api/query", json={"query": "What caused the Eagle-5 yield drop?"})
    body = resp.json()
    assert resp.status_code == 200
    top = body["results"][0]
    assert top["source_file"].endswith("meeting_01_eagle5_yield.md")
    assert top["attendees"] and top["topic_domain"]
    assert body["retrieval"]["reranker"] == "llm"
    assert body["retrieval"]["semantic_candidates"] > 0
    assert body["retrieval"]["bm25_candidates"] > 0
    assert body["answer"] and "[" in body["answer"]
    assert any(d["source_file"] == top["source_file"] for d in body["documents"])

    # Exact-term query: BM25 should surface lot 4412 mentions.
    lot = client.post(
        "/api/query", json={"query": "lot 4412", "generate_answer": False, "rerank": False}
    ).json()
    assert all("4412" in r["text"] for r in lot["results"][:2])

    # Metadata filter.
    filtered = client.post(
        "/api/query",
        json={"query": "schedule", "filters": {"person": "Priya"}, "generate_answer": False},
    ).json()
    assert filtered["results"]
    assert all("Priya Patel" in r["attendees"] for r in filtered["results"])

    # Removing a source file prunes it on the next ingest.
    (isolated_env / "meetings" / "meeting_12_customer_escalation.md").unlink()
    pruned = client.post("/api/ingest").json()
    assert pruned["removed"] == 1
    assert len(client.get("/api/documents").json()) == 2
