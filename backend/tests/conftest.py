import shutil
from pathlib import Path

import httpx
import pytest

from app.main import reset_all

FIXTURES = Path(__file__).parent / "fixtures"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_LLM = "qwen2.5:7b"
OLLAMA_EMBED = "nomic-embed-text"


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test gets its own data dir, SQLite file and Chroma dir."""
    data_dir = tmp_path / "data"
    shutil.copytree(FIXTURES / "meetings", data_dir / "meetings")
    env = {
        "APP_ENV": "test",
        "DATA_DIR": str(data_dir),
        "CHROMA_DIR": str(tmp_path / "chroma"),
        "SQLITE_PATH": str(tmp_path / "app.db"),
        "SEED_DIR": str(tmp_path / "no-seed"),
        "USE_DOCLING": "false",
        "LLM_PROVIDER": "ollama",
        "LLM_MODEL": OLLAMA_LLM,
        "EMBEDDING_PROVIDER": "ollama",
        "EMBEDDING_MODEL": OLLAMA_EMBED,
        "OLLAMA_BASE_URL": OLLAMA_URL,
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    reset_all()
    yield data_dir
    reset_all()


def _ollama_ready() -> bool:
    try:
        names = {m["name"] for m in httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2).json()["models"]}
    except Exception:
        return False
    return OLLAMA_LLM in names and any(n.startswith(OLLAMA_EMBED) for n in names)


requires_ollama = pytest.mark.skipif(
    not _ollama_ready(), reason=f"Ollama with {OLLAMA_LLM} + {OLLAMA_EMBED} not available"
)
