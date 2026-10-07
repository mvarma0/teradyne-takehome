"""Provider selection in the model factory (app/llm.py). Builds clients only; no network calls."""

import pytest

from app import llm
from app.main import reset_all


def _use(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    monkeypatch.setattr(llm, "dotenv_values", lambda _path: {})  # ignore a local .env
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    reset_all()


def test_missing_key_raises_config_error(monkeypatch: pytest.MonkeyPatch):
    _use(monkeypatch, LLM_PROVIDER="openai", LLM_MODEL="gpt-4o-mini", OPENAI_API_KEY="")
    with pytest.raises(llm.ConfigError, match="OPENAI_API_KEY"):
        llm.get_llm()


def test_uninstalled_provider_raises_config_error(monkeypatch: pytest.MonkeyPatch):
    _use(monkeypatch, LLM_PROVIDER="not_a_provider", LLM_MODEL="x")
    with pytest.raises(llm.ConfigError, match="not_a_provider"):
        llm.get_llm()


@pytest.mark.parametrize(
    ("provider", "model", "key_var", "cls_name"),
    [
        ("openai", "gpt-4o-mini", "OPENAI_API_KEY", "ChatOpenAI"),
        ("google_genai", "gemini-3.1-flash-lite", "GOOGLE_API_KEY", "ChatGoogleGenerativeAI"),
        ("ollama", "qwen2.5:7b", None, "ChatOllama"),
    ],
)
def test_presets_build_from_config(monkeypatch, provider, model, key_var, cls_name):
    env = {"LLM_PROVIDER": provider, "LLM_MODEL": model}
    if key_var:
        env[key_var] = "test-key"
    _use(monkeypatch, **env)
    assert type(llm.get_llm()).__name__ == cls_name
    assert llm.llm_identity() == f"{provider}:{model}"


def test_openai_compatible_endpoint_needs_no_openai_key(monkeypatch: pytest.MonkeyPatch):
    _use(
        monkeypatch,
        LLM_PROVIDER="openai",
        LLM_MODEL="local-model",
        OPENAI_API_KEY="",
        LLM_BASE_URL="http://localhost:1234/v1",
        LLM_API_KEY="anything",
    )
    assert type(llm.get_llm()).__name__ == "ChatOpenAI"


def test_embeddings_and_collection_follow_provider(monkeypatch: pytest.MonkeyPatch):
    _use(
        monkeypatch,
        EMBEDDING_PROVIDER="google_genai",
        EMBEDDING_MODEL="gemini-embedding-001",
        GOOGLE_API_KEY="test-key",
    )
    assert type(llm.get_embeddings()).__name__ == "GoogleGenerativeAIEmbeddings"
    assert llm.collection_name() == "fastchip__google-genai-gemini-embedding-001"


def test_nomic_embeddings_get_task_prefixes(monkeypatch: pytest.MonkeyPatch):
    _use(monkeypatch, EMBEDDING_PROVIDER="ollama", EMBEDDING_MODEL="nomic-embed-text")
    assert isinstance(llm.get_embeddings(), llm.PrefixedEmbeddings)


def test_rpm_limiter_allows_one_question_burst_but_caps_the_minute():
    limiter = llm.rpm_limiter(14)
    # A fresh process can send a whole question's calls at once ...
    assert all(limiter.acquire(blocking=False) for _ in range(14))
    # ... and is then throttled back to the per-minute rate.
    assert limiter.acquire(blocking=False) is False
