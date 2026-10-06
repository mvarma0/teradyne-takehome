"""Provider selection in the model factory. Builds clients only; no network calls."""

import pytest

from app.llm import factory
from app.state import reset_all


def _use(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    monkeypatch.setattr(factory, "dotenv_values", lambda _path: {})  # ignore a local .env
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    reset_all()


def test_missing_key_raises_config_error(monkeypatch: pytest.MonkeyPatch):
    _use(monkeypatch, LLM_PROVIDER="openai", LLM_MODEL="gpt-4o-mini", OPENAI_API_KEY="")
    with pytest.raises(factory.ConfigError, match="OPENAI_API_KEY"):
        factory.get_llm()


def test_uninstalled_provider_raises_config_error(monkeypatch: pytest.MonkeyPatch):
    _use(monkeypatch, LLM_PROVIDER="not_a_provider", LLM_MODEL="x")
    with pytest.raises(factory.ConfigError, match="not_a_provider"):
        factory.get_llm()


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
    assert type(factory.get_llm()).__name__ == cls_name
    assert factory.llm_identity() == f"{provider}:{model}"


def test_openai_compatible_endpoint_needs_no_openai_key(monkeypatch: pytest.MonkeyPatch):
    _use(
        monkeypatch,
        LLM_PROVIDER="openai",
        LLM_MODEL="local-model",
        OPENAI_API_KEY="",
        LLM_BASE_URL="http://localhost:1234/v1",
        LLM_API_KEY="anything",
    )
    assert type(factory.get_llm()).__name__ == "ChatOpenAI"


def test_embeddings_and_collection_follow_provider(monkeypatch: pytest.MonkeyPatch):
    _use(
        monkeypatch,
        EMBEDDING_PROVIDER="google_genai",
        EMBEDDING_MODEL="gemini-embedding-001",
        GOOGLE_API_KEY="test-key",
    )
    assert type(factory.get_embeddings()).__name__ == "GoogleGenerativeAIEmbeddings"
    assert factory.collection_name() == "fastchip__google-genai-gemini-embedding-001"


def test_nomic_embeddings_get_task_prefixes(monkeypatch: pytest.MonkeyPatch):
    _use(monkeypatch, EMBEDDING_PROVIDER="ollama", EMBEDDING_MODEL="nomic-embed-text")
    assert isinstance(factory.get_embeddings(), factory.PrefixedEmbeddings)
