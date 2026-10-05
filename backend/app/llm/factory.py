"""The only place LLM / embedding clients are constructed."""

import re
from functools import lru_cache
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from app.config import get_settings


class ConfigError(RuntimeError):
    """Raised when configuration prevents a provider from being built."""


def _require_openai_key() -> str:
    key = get_settings().openai_api_key
    if not key:
        raise ConfigError(
            "OPENAI_API_KEY is not set (backend/.env). Set it, or switch the provider to ollama."
        )
    return key


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


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    s = get_settings()
    if s.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=s.llm_model, temperature=s.llm_temperature, base_url=s.ollama_base_url
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=s.llm_model, temperature=s.llm_temperature, api_key=_require_openai_key()
    )


def structured_llm(schema: type) -> Runnable[Any, Any]:
    """LLM bound to a Pydantic output schema, using the method each provider handles best."""
    method = "json_schema" if get_settings().llm_provider == "ollama" else "function_calling"
    return get_llm().with_structured_output(schema, method=method)


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    s = get_settings()
    if s.embedding_provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        inner: Embeddings = OllamaEmbeddings(model=s.embedding_model, base_url=s.ollama_base_url)
        if "nomic" in s.embedding_model:
            return PrefixedEmbeddings(inner, "search_document: ", "search_query: ")
        return inner
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=s.embedding_model, api_key=_require_openai_key())


def llm_identity() -> str:
    s = get_settings()
    return f"{s.llm_provider}:{s.llm_model}"


def collection_name() -> str:
    """Collection is suffixed with the embedding model so vectors never mix across models."""
    s = get_settings()
    suffix = re.sub(r"[^a-zA-Z0-9]+", "-", f"{s.embedding_provider}-{s.embedding_model}")
    return f"{s.chroma_collection}__{suffix.strip('-').lower()}"[:63]
