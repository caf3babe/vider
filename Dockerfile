# ── Stage 1: build React frontend ─────────────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ── Stage 2: install Python deps on build host (no QEMU) ──────────────────────
FROM --platform=$BUILDPLATFORM python:3.12-slim AS python-deps

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./

ARG TARGETPLATFORM
RUN case "${TARGETPLATFORM:-linux/amd64}" in \
    "linux/amd64") UV_PLATFORM="x86_64-unknown-linux-gnu" ;; \
    "linux/arm64") UV_PLATFORM="aarch64-unknown-linux-gnu" ;; \
    *)             UV_PLATFORM="x86_64-unknown-linux-gnu" ;; \
    esac && \
    uv sync --frozen --no-dev --no-install-project --python-platform "$UV_PLATFORM"

# ── Stage 3: production image ──────────────────────────────────────────────────
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=python-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY backend/main.py ./
COPY --from=frontend-builder /app/frontend/dist ./static

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
