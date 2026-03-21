# ── Stage 1: Build deps ───────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 2: Production image ─────────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="hello@contextmesh.dev"
LABEL org.opencontainers.image.title="ContextMesh API"
LABEL org.opencontainers.image.version="1.0.0"

RUN useradd -m -u 1001 -s /bin/bash contextmesh

WORKDIR /app

COPY --from=builder /install /usr/local

# Copy API source and billing routes
COPY --chown=contextmesh:contextmesh api/ .
COPY --chown=contextmesh:contextmesh billing/ ./billing/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    WORKERS=2 \
    CONTEXTMESH_ENV=production

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

USER contextmesh
EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT --workers $WORKERS --timeout-graceful-shutdown 30"]
