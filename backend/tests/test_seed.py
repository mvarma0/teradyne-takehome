from pathlib import Path

import pytest

from app.config import get_settings
from app.main import seed_storage


def _make_seed(root: Path) -> Path:
    seed = root / "seed"
    (seed / "chroma").mkdir(parents=True)
    (seed / "app.db").write_bytes(b"seed-db")
    (seed / "chroma" / "chroma.sqlite3").write_bytes(b"seed-chroma")
    return seed


def test_seed_copies_into_empty_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SEED_DIR", str(_make_seed(tmp_path)))
    get_settings.cache_clear()
    s = get_settings()

    assert seed_storage() is True
    assert s.sqlite_path.read_bytes() == b"seed-db"
    assert (s.chroma_dir / "chroma.sqlite3").read_bytes() == b"seed-chroma"


def test_seed_never_overwrites_existing_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SEED_DIR", str(_make_seed(tmp_path)))
    get_settings.cache_clear()
    s = get_settings()
    s.sqlite_path.write_bytes(b"local-chats")

    assert seed_storage() is False
    assert s.sqlite_path.read_bytes() == b"local-chats"
    assert not s.chroma_dir.exists()


def test_no_seed_is_a_no_op():
    s = get_settings()
    assert seed_storage() is False
    assert not s.sqlite_path.exists()
