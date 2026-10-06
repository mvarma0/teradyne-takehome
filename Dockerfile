# syntax=docker/dockerfile:1
# FastChip Knowledge System: API + built React app in one container (e.g. Render free tier).
# Build:  docker build -t fastchip .
# Run:    docker run -p 8000:8000 --env-file backend/.env fastchip   → http://localhost:8000

# ---- 1. frontend ------------------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. backend -------------------------------------------------------------------------
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH

RUN useradd --create-home --uid 1000 app
WORKDIR /app/backend

# Dependencies first so code changes don't reinstall them (no dev tools, no PyTorch).
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY data/ /app/data/
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# storage/ starts empty: on startup the app copies the chat-free index from seed/ into it.
# data/ stays writable for uploads from the Documents page.
RUN mkdir -p storage && chown -R app:app storage /app/data
USER app

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
