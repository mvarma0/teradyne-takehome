"""FastAPI application entry point."""

import logging
import shutil
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app import api
from app.config import get_settings
from app.db import init_db
from app.ingest import _encoding
from app.llm import ConfigError, get_embeddings, get_llm
from app.search import get_vectorstore, invalidate_bm25

# ---- state --------------------------------------------------------------------------------
# Reset cached singletons (settings, models, vector store, BM25). Used after config changes.


def reset_all() -> None:
    for fn in (get_settings, get_llm, get_embeddings, get_vectorstore, _encoding):
        fn.cache_clear()
    invalidate_bm25()


# ---- seed ---------------------------------------------------------------------------------
# A fresh checkout (or container) starts from the committed, chat-free index in backend/seed/
# instead of re-ingesting data/. Only copied when storage is empty, so local data is never
# overwritten. The seed holds one Chroma collection per embedding model; other models re-ingest.


def seed_storage() -> bool:
    s = get_settings()
    seed_db, seed_chroma = s.seed_dir / "app.db", s.seed_dir / "chroma"
    if s.sqlite_path.exists() or s.chroma_dir.exists() or not seed_db.exists():
        return False
    s.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(seed_db, s.sqlite_path)
    if seed_chroma.is_dir():
        shutil.copytree(seed_chroma, s.chroma_dir)
    logging.getLogger(__name__).info("seeded storage from %s", s.seed_dir)
    return True


# ---- frontend -----------------------------------------------------------------------------
# In a deployment (Docker) the built React app is served from the same origin as the API.
# Unknown paths fall back to index.html so client-side routes survive a reload. In local dev
# Vite serves the UI on :5173 and this is a no-op unless frontend/dist has been built.


def mount_frontend(target: FastAPI) -> bool:
    dist = get_settings().frontend_dist.resolve()
    index = dist / "index.html"
    if not index.is_file():
        return False

    @target.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(dist):
            return FileResponse(file)
        return FileResponse(index)

    return True


# ---- main ---------------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed_storage()
    init_db()
    yield


app = FastAPI(title="FastChip Knowledge API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ConfigError)
async def _config_error(_: Request, exc: ConfigError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(ConnectionError)
@app.exception_handler(httpx.ConnectError)
async def _provider_unreachable(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": f"Model provider unreachable (is Ollama running?): {exc}"},
    )


app.include_router(api.router)
mount_frontend(app)
