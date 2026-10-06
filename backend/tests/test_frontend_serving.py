from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import api
from app.config import get_settings
from app.main import mount_frontend


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, built: bool = True) -> TestClient:
    dist = tmp_path / "dist"
    if built:
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<html>app</html>")
        (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("outside dist")
    monkeypatch.setenv("FRONTEND_DIST", str(dist))
    get_settings.cache_clear()
    target = FastAPI()
    target.include_router(api.router)
    assert mount_frontend(target) is built
    return TestClient(target)


def test_serves_index_assets_and_client_routes(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/").text == "<html>app</html>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/review").text == "<html>app</html>"  # client-side route on reload


def test_api_routes_win_and_unknown_api_paths_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/does-not-exist").status_code == 404


def test_no_files_outside_dist(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert "outside dist" not in client.get("/../secret.txt").text
    assert "outside dist" not in client.get("/%2e%2e/secret.txt").text


def test_no_build_means_no_frontend_route(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, built=False)
    assert client.get("/").status_code == 404
