import pytest
from fastapi.testclient import TestClient

from app import api
from app.llm import is_rate_limited
from app.main import app


class RateLimitError(Exception):  # same class name the openai/anthropic SDKs use
    pass


class ResourceExhausted(Exception):  # google.api_core's name for HTTP 429
    pass


class HttpError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def test_rate_limit_errors_are_recognised_across_providers():
    assert is_rate_limited(RateLimitError("too many requests"))
    assert is_rate_limited(ResourceExhausted("quota"))
    assert is_rate_limited(HttpError(429))
    assert is_rate_limited(RuntimeError("Error calling model (RESOURCE_EXHAUSTED): 429"))
    try:
        try:
            raise HttpError(429)
        except HttpError as inner:
            raise ValueError("wrapped") from inner
    except ValueError as wrapped:
        assert is_rate_limited(wrapped)
    assert not is_rate_limited(HttpError(500))
    assert not is_rate_limited(ValueError("bad input"))


def _raise(exc: Exception):
    def fn(*_args, **_kwargs):
        raise exc

    return fn


def test_query_returns_503_with_a_reason_when_the_provider_is_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(api, "answer", _raise(RateLimitError("429 quota exceeded")))
    resp = TestClient(app, raise_server_exceptions=False).post("/api/query", json={"query": "x"})
    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "60"
    assert "rate limit or quota" in resp.json()["detail"]


def test_other_errors_stay_500_with_a_json_detail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "answer", _raise(KeyError("boom")))
    resp = TestClient(app, raise_server_exceptions=False).post("/api/query", json={"query": "x"})
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal error (KeyError)"}


def test_chat_stream_reports_rate_limits_as_a_readable_error_event(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(api, "run_chat", _raise(RateLimitError("429")))
    resp = TestClient(app).post("/api/chat/stream", json={"message": "x"})
    assert "event: error" in resp.text and "rate limit or quota" in resp.text
