import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes, routes_chat, routes_review
from app.config import get_settings
from app.db.sqlite import init_db
from app.llm.factory import ConfigError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
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


for module in (routes, routes_chat, routes_review):
    app.include_router(module.router)
