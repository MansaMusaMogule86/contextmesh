# ── Stage 1: Build deps ───────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies into a prefix so we can copy them cleanly
COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 2: Production image ─────────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="hello@contextmesh.dev"
LABEL org.opencontainers.image.title="ContextMesh API"
LABEL org.opencontainers.image.description="Persistent memory layer for AI agents"
LABEL org.opencontainers.image.version="1.0.0"

# Non-root user for security
RUN useradd -m -u 1001 -s /bin/bash contextmesh

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=contextmesh:contextmesh . .

# Runtime environment defaults (override via env vars or fly.toml)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    WORKERS=2 \
    CONTEXTMESH_ENV=production

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')"

USER contextmesh
EXPOSE $PORT

# Uvicorn with graceful shutdown support
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT --workers $WORKERS --timeout-graceful-shutdown 30"]
