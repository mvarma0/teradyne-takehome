"""Central configuration. Every tunable comes from env / backend/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

Provider = Literal["openai", "ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # LLM: enrichment, answer generation, reranking
    llm_provider: Provider = "openai"
    llm_model: str = "gpt-4o-mini"  # ollama e.g. qwen2.5:7b
    llm_temperature: float = 0.0

    # Embeddings
    embedding_provider: Provider = "openai"
    embedding_model: str = "text-embedding-3-small"  # ollama e.g. nomic-embed-text

    # Ingestion: docling parsing + structure-aware recursive chunking (token budgets)
    use_docling: bool = True
    chunk_max_tokens: int = 512
    chunk_min_tokens: int = 80
    chunk_overlap_tokens: int = 64
    enrich_max_chars: int = 12000

    # Retrieval: semantic + BM25 fused with weighted RRF, then reranked
    top_k: int = 6
    candidate_k: int = 20
    semantic_weight: float = 1.0
    bm25_weight: float = 1.0
    rrf_k: int = 60
    reranker: Literal["llm", "none"] = "llm"
    rerank_top_n: int = 10  # fused candidates sent to the reranker
    rerank_concurrency: int = 4
    rerank_max_chars: int = 1200

    # Answering, guardrails, routing
    confidence_threshold: float = 0.55
    min_retrieval_score: float = 0.25
    history_messages: int = 6  # previous chat messages used for follow-ups
    guardrails_llm: bool = True  # LLM input classifier (heuristics always run)
    routing_max_people: int = 3

    # Quality alerts (monitoring)
    alert_min_answer_rate: float = 0.6
    alert_max_negative_feedback_rate: float = 0.2
    alert_min_mean_confidence: float = 0.5
    alert_min_citation_valid_ratio: float = 0.9
    alert_max_p95_latency_ms: int = 20000
    alert_baseline_drop_pct: float = 0.15
    alert_min_samples: int = 5

    # Storage
    data_dir: Path = BACKEND_DIR.parent / "data"
    chroma_dir: Path = BACKEND_DIR / "storage" / "chroma"
    chroma_collection: str = "fastchip"
    sqlite_path: Path = BACKEND_DIR / "storage" / "app.db"

    # API
    cors_origins: str = "http://localhost:5173"

    @field_validator("data_dir", "chroma_dir", "sqlite_path")
    @classmethod
    def _resolve_relative_to_backend(cls, v: Path) -> Path:
        return v if v.is_absolute() else (BACKEND_DIR / v).resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def meetings_dir(self) -> Path:
        return self.data_dir / "meetings"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
