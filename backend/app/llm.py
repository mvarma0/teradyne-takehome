"""The only place LLM / embedding clients are constructed.

Providers are LangChain provider ids, built with ``init_chat_model`` / ``init_embeddings``,
so switching provider is a config change: set ``LLM_PROVIDER`` / ``EMBEDDING_PROVIDER``
and the model names in ``backend/.env``. ``openai``, ``google_genai`` and ``ollama`` ship
with the project; any other LangChain provider works after ``uv add langchain-<provider>``.
OpenAI-compatible endpoints (vLLM, LM Studio, GitHub Models, ...) use provider ``openai``
with ``LLM_BASE_URL``."""

import os
import re
from functools import lru_cache
from typing import Any

from dotenv import dotenv_values
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import Runnable

from app.config import BACKEND_DIR, Settings, get_settings


class ConfigError(RuntimeError):
    """Raised when configuration prevents a provider from being built."""


# Settings field / environment variable holding each provider's API key.
_KEY_VARS = {
    "openai": "openai_api_key",
    "azure_openai": "azure_openai_api_key",
    "google_genai": "google_api_key",
    "anthropic": "anthropic_api_key",
    "groq": "groq_api_key",
    "mistralai": "mistral_api_key",
    "cohere": "cohere_api_key",
    "deepseek": "deepseek_api_key",
    "fireworks": "fireworks_api_key",
    "together": "together_api_key",
    "openrouter": "openrouter_api_key",
}
_LOCAL_PROVIDERS = {"ollama"}

# Structured-output method each provider handles best; anything else uses function calling.
_STRUCTURED_METHOD = {"ollama": "json_schema", "google_genai": "json_schema"}


def _api_key(provider: str, explicit: str, base_url: str) -> str | None:
    """Explicit key, else the provider's key from settings (.env) or the environment."""
    if explicit:
        return explicit
    if provider in _LOCAL_PROVIDERS:
        return None
    field = _KEY_VARS.get(provider)
    if field is None:
        return None  # unknown provider: let its integration read its own environment
    env_var = field.upper()
    key = (
        getattr(get_settings(), field, "")
        or os.environ.get(env_var, "")
        or (dotenv_values(BACKEND_DIR / ".env").get(env_var) or "")
    )
    if not key and not base_url:
        raise ConfigError(
            f"{env_var} is not set (backend/.env or environment). "
            f"Set it, or switch the {provider} provider to another one (e.g. ollama)."
        )
    return key or None


def _client_kwargs(provider: str, api_key: str | None, base_url: str, s: Settings) -> dict:
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if provider == "ollama":
        kwargs["base_url"] = base_url or s.ollama_base_url
    elif base_url:
        kwargs["base_url"] = base_url
    return kwargs


class PrefixedEmbeddings(Embeddings):
    """Adds task prefixes required by models such as nomic-embed-text."""

    def __init__(self, inner: Embeddings, doc_prefix: str, query_prefix: str) -> None:
        self.inner = inner
        self.doc_prefix = doc_prefix
        self.query_prefix = query_prefix

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.inner.embed_documents([self.doc_prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self.inner.embed_query(self.query_prefix + text)


def rpm_limiter(rpm: int) -> InMemoryRateLimiter:
    """Client-side cap of `rpm` requests/minute that still allows bursts.

    A question makes several calls at once (guardrail, rewrite, parallel rerank, answer). With a
    bucket of 1 they were spaced 60/rpm seconds apart (~35 s per question at 14 RPM); a bucket of
    `rpm` that starts full lets one question's calls go through immediately, while the refill
    rate keeps the average under the provider's per-minute limit.
    """
    limiter = InMemoryRateLimiter(requests_per_second=rpm / 60, max_bucket_size=rpm)
    limiter.available_tokens = float(rpm)
    return limiter


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    from langchain.chat_models import init_chat_model

    s = get_settings()
    kwargs = _client_kwargs(
        s.llm_provider, _api_key(s.llm_provider, s.llm_api_key, s.llm_base_url), s.llm_base_url, s
    )
    if s.llm_max_rpm > 0:
        kwargs["rate_limiter"] = rpm_limiter(s.llm_max_rpm)
    if s.llm_provider not in _LOCAL_PROVIDERS:
        kwargs["max_retries"] = s.llm_max_retries
    try:
        return init_chat_model(
            s.llm_model, model_provider=s.llm_provider, temperature=s.llm_temperature, **kwargs
        )
    except (ImportError, ValueError) as exc:
        raise ConfigError(f"Cannot build LLM {llm_identity()}: {exc}") from exc


def structured_llm(schema: type) -> Runnable[Any, Any]:
    """LLM bound to a Pydantic output schema, using the method each provider handles best."""
    s = get_settings()
    method = s.llm_structured_output
    if method == "auto":
        method = _STRUCTURED_METHOD.get(s.llm_provider, "function_calling")
    return get_llm().with_structured_output(schema, method=method)


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    from langchain.embeddings import init_embeddings

    s = get_settings()
    provider = s.embedding_provider
    kwargs = _client_kwargs(
        provider,
        _api_key(provider, s.embedding_api_key, s.embedding_base_url),
        s.embedding_base_url,
        s,
    )
    try:
        inner = init_embeddings(s.embedding_model, provider=provider, **kwargs)
    except (ImportError, ValueError) as exc:
        raise ConfigError(f"Cannot build embeddings {provider}:{s.embedding_model}: {exc}") from exc
    if "nomic" in s.embedding_model:
        return PrefixedEmbeddings(inner, "search_document: ", "search_query: ")
    return inner


def llm_identity() -> str:
    s = get_settings()
    return f"{s.llm_provider}:{s.llm_model}"


def collection_name() -> str:
    """Collection is suffixed with the embedding model so vectors never mix across models."""
    s = get_settings()
    suffix = re.sub(r"[^a-zA-Z0-9]+", "-", f"{s.embedding_provider}-{s.embedding_model}")
    return f"{s.chroma_collection}__{suffix.strip('-').lower()}"[:63]
