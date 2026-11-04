FROM ghcr.io/astral-sh/uv:0.11.7 AS uv

FROM node:22-bookworm-slim AS studio-ui
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY src/wren_semantic/static/ /build/src/wren_semantic/static/
RUN npm run build

FROM python:3.11-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/tmp \
    TOKIO_WORKER_THREADS=2 \
    RAYON_NUM_THREADS=2 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY --from=studio-ui /build/src/wren_semantic/static/ ./src/wren_semantic/static/
RUN uv sync --frozen --no-dev --no-editable
COPY models ./models
RUN mkdir -p /state/studio && chown -R 10001:10001 /state

USER 10001:10001
EXPOSE 8090
CMD ["python", "-m", "uvicorn", "wren_semantic.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8090", "--workers", "1", "--limit-concurrency", "32", "--no-access-log"]
