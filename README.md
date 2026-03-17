# ContextMesh

**Persistent memory layer for AI agents.**

Every agent starts blind. ContextMesh gives them shared memory.

## What it is

A simple API + vector store that any AI agent (Claude, Cursor, custom) can write context to and read from. Namespaced per workspace. Semantic search. Cross-tool, cross-session.

## Structure

```
contextmesh/
  api/
    vector_store.py   # Qdrant wrapper — embed, store, query
    embedder.py       # text → 1536-dim vector (OpenAI ada-002)
    main.py           # FastAPI — 4 endpoints
    auth.py           # API key validation + plan limits
    requirements.txt
  mcp_server.py       # MCP protocol server (stdio)
  sdk/
    contextmesh.py    # Python SDK
    contextmesh.js    # JS/TS SDK
  dashboard/
    index.html        # Web dashboard
  landing/
    index.html        # Marketing landing page
  infra/
    docker-compose.yml
```

## Quick Start

### 1. Run locally

```bash
cd infra
OPENAI_API_KEY=sk-... docker-compose up
```

### 2. Generate a dev key

```bash
curl -X POST "http://localhost:8000/dev/generate-key?workspace_id=myteam&plan=team"
```

### 3. Use the Python SDK

```python
from contextmesh import Mesh
mesh = Mesh("cm_live_your_key", base_url="http://localhost:8000")

mesh.remember("prod DB is postgres 15 on AWS us-east-1", tags=["database"])
results = mesh.query("what should I know about our database?")
```

### 4. Use the MCP server

Add to `~/.cursor/mcp.json` or `~/.claude/mcp.json`:

```json
{
  "contextmesh": {
    "command": "python3",
    "args": ["/path/to/contextmesh/mcp_server.py"],
    "env": {
      "CM_KEY": "cm_live_your_key",
      "CM_URL": "http://localhost:8000"
    }
  }
}
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /remember | Store context |
| POST | /query | Semantic search |
| DELETE | /forget/{id} | Remove entry |
| GET | /list | Browse entries |
| GET | /usage | Check plan usage |
| GET | /health | Liveness check |

## Deploy to Fly.io

```bash
fly launch
fly secrets set OPENAI_API_KEY=sk-... REDIS_URL=redis://...
fly deploy
```

## Pricing (production)

| Plan | Price | Workspaces | Entries | Queries/mo |
|------|-------|-----------|---------|-----------|
| Solo | $19/mo | 1 | 500k | 100k |
| Team | $99/mo | 10 | 5M | 1M |
| Enterprise | $599/mo | ∞ | ∞ | ∞ |
