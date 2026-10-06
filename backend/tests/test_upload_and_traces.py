from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import api, db
from app.db import init_db
from app.ingest import IngestReport
from app.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Upload tests check file placement; ingestion itself is covered elsewhere.
    monkeypatch.setattr(api, "run_ingestion", lambda: IngestReport(collection="test"))
    init_db()
    return TestClient(app)


def _upload(client: TestClient, name: str, body: bytes = b"content"):
    return client.post("/api/documents/upload", params={"filename": name}, content=body)


def test_upload_places_files_where_ingestion_finds_them(client: TestClient, isolated_env: Path):
    r = _upload(client, "new_meeting.md")
    assert r.status_code == 200
    assert r.json()["source_file"] == "meetings/new_meeting.md"
    assert r.json()["replaced"] is False

    r = _upload(client, "report.docx")
    assert r.json()["source_file"] == "documents/docx/report.docx"
    assert (isolated_env / "documents/docx/report.docx").read_bytes() == b"content"

    r = _upload(client, "report.docx", b"v2")
    assert r.json()["replaced"] is True
    assert (isolated_env / "documents/docx/report.docx").read_bytes() == b"v2"


def test_upload_rejects_bad_names_and_types(client: TestClient, isolated_env: Path):
    assert _upload(client, "evil.exe").status_code == 415
    assert _upload(client, "..").status_code == 400
    assert _upload(client, "empty.md", b"").status_code == 400
    # Directory parts are stripped, so a traversal attempt lands inside meetings/.
    r = _upload(client, "../../escape.md")
    assert r.json()["source_file"] == "meetings/escape.md"
    assert not (isolated_env.parent / "escape.md").exists()


def test_traces_list_and_detail(client: TestClient):
    conv = db.create_conversation("q")
    payload = {
        "citations": [
            {"n": 1, "source_file": "meetings/a.md"},
            {"n": 2, "source_file": "documents/docx/b.docx"},
        ],
        "cited": [2],
        "guardrails": {"category": "knowledge_question"},
        "latency_ms": 1200,
    }
    db.add_assistant_message(
        "m1", conv["id"], "answer", "What?", "What?", None, payload, 0.4, False, "routed"
    )
    db.create_gap("m1", "low_confidence", "What?", "answer", reason="low")

    [row] = client.get("/api/traces").json()
    assert row["id"] == "m1"
    assert (row["n_retrieved"], row["n_cited"]) == (2, 1)
    assert row["cited_files"] == ["documents/docx/b.docx"]
    assert row["n_gaps"] == 1

    detail = client.get("/api/traces/m1").json()
    assert detail["query"] == "What?"
    assert detail["status"] == "routed"
    assert [g["type"] for g in detail["gaps"]] == ["low_confidence"]
    assert client.get("/api/traces/nope").status_code == 404


def test_upload_lowercases_the_extension(client: TestClient, isolated_env: Path):
    r = _upload(client, "Weekly_Sync.MD")
    assert r.json()["source_file"] == "meetings/Weekly_Sync.md"
    assert (isolated_env / "meetings/Weekly_Sync.md").exists()
