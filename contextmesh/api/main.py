"""
ContextMesh — API
4 endpoints. That's it.

POST   /remember  — write context
POST   /query     — semantic search
DELETE /forget    — remove entry
GET    /list      — browse stored entries
GET    /usage     — check plan usage
GET    /health    — liveness check
"""

import os
import time
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from vector_store import VectorStore
from embedder    import Embedder
from auth        import require_auth, AuthManager, _auth

# Billing — import conditionally so API still works without Stripe configured
try:
    import sys, os as _os
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..", "billing"))
    from paddle_routes import router as billing_router
    _BILLING_ENABLED = True
except ImportError:
    _BILLING_ENABLED = False

# ── Init ─────────────────────────────────────────────────────────────────────

store    = VectorStore()
embedder = Embedder()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("ContextMesh starting up...")
    yield
    print("ContextMesh shutting down...")

app = FastAPI(
    title       = "ContextMesh API",
    description = "Persistent memory layer for AI agents",
    version     = "1.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# Mount billing routes if Stripe is configured
if _BILLING_ENABLED:
    app.include_router(billing_router)

# ── Request / Response models ─────────────────────────────────────────────────

class RememberRequest(BaseModel):
    text:         str            = Field(..., min_length=1, max_length=10_000, description="The context to store")
    tags:         list[str]      = Field(default=[], description="Optional tags for filtering")
    source_agent: Optional[str]  = Field(None, description="Which agent wrote this (e.g. 'cursor', 'claude', 'custom')")
    confidence:   float          = Field(1.0, ge=0.0, le=1.0, description="How confident you are in this context (0–1)")

class QueryRequest(BaseModel):
    q:          str           = Field(..., min_length=1, max_length=2_000, description="Natural language query")
    top_k:      int           = Field(5, ge=1, le=20)
    tag_filter: Optional[str] = Field(None, description="Only return entries with this tag")
    min_score:  float         = Field(0.3, ge=0.0, le=1.0, description="Minimum similarity score (0–1)")

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "contextmesh", "ts": int(time.time())}


@app.post("/remember")
async def remember(
    body:      RememberRequest,
    workspace: dict = Depends(require_auth),
):
    """
    Store a piece of context. Any agent can call this.
    The text is embedded and stored with metadata.
    Returns the entry ID so you can delete it later.
    """
    wid    = workspace["workspace_id"]
    vector = await embedder.embed(body.text)

    entry_id = store.write(
        workspace_id = wid,
        text         = body.text,
        vector       = vector,
        tags         = body.tags,
        source_agent = body.source_agent,
        confidence   = body.confidence,
    )

    await _auth.increment_queries(wid)

    return {
        "id":      entry_id,
        "status":  "stored",
        "chars":   len(body.text),
        "tags":    body.tags,
    }


@app.post("/query")
async def query(
    body:      QueryRequest,
    workspace: dict = Depends(require_auth),
):
    """
    Semantic search over this workspace's context.
    Returns the top-K most relevant entries ranked by similarity.
    """
    wid    = workspace["workspace_id"]
    vector = await embedder.embed(body.q)

    results = store.query(
        workspace_id = wid,
        query_vector = vector,
        top_k        = body.top_k,
        tag_filter   = body.tag_filter,
        min_score    = body.min_score,
    )

    await _auth.increment_queries(wid)

    return {
        "query":   body.q,
        "count":   len(results),
        "results": results,
    }


@app.delete("/forget/{entry_id}")
async def forget(
    entry_id:  str,
    workspace: dict = Depends(require_auth),
):
    """
    Remove a specific context entry by ID.
    Get the ID from /remember or /list.
    """
    wid     = workspace["workspace_id"]
    deleted = store.forget(wid, entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")
    return {"id": entry_id, "status": "deleted"}


@app.get("/list")
async def list_entries(
    limit:      int           = Query(50, ge=1, le=200),
    offset:     int           = Query(0, ge=0),
    tag_filter: Optional[str] = Query(None),
    workspace:  dict          = Depends(require_auth),
):
    """
    Browse what's stored in this workspace.
    Paginate with limit + offset.
    """
    wid     = workspace["workspace_id"]
    entries = store.list_entries(wid, limit=limit, offset=offset, tag_filter=tag_filter)
    stats   = store.stats(wid)

    return {
        "total":   stats["total_entries"],
        "offset":  offset,
        "limit":   limit,
        "entries": entries,
    }


@app.get("/usage")
async def usage(workspace: dict = Depends(require_auth)):
    """
    Check how much of your plan you've used this month.
    """
    wid  = workspace["workspace_id"]
    plan = workspace["plan"]
    u    = await _auth.get_usage(wid, plan)
    s    = store.stats(wid)
    return {
        "workspace_id":    wid,
        "plan":            plan,
        "queries_used":    u["queries_used"],
        "queries_limit":   u["queries_limit"],
        "entries_stored":  s["total_entries"],
        "entries_limit":   u["entries_limit"],
        "rate_limit_rpm":  u["rate_limit_per_min"],
    }


# ── Dev helper: generate a key (disabled in prod) ─────────────────────────────

if os.getenv("CONTEXTMESH_ENV") == "development":
    @app.post("/dev/generate-key")
    async def dev_generate_key(workspace_id: str, plan: str = "team"):
        key = await _auth.generate_key(workspace_id=workspace_id, plan=plan, label="dev")
        return {"api_key": key, "workspace_id": workspace_id, "plan": plan}
