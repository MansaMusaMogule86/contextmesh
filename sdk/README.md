# contextmesh

**Persistent semantic memory for AI agents** — store, search, and retrieve context across sessions.

## Install

```bash
pip install contextmesh
```

## Quick start

```python
from contextmesh import Mesh

mesh = Mesh("cm_live_your_key")  # get a key at https://contextmesh.dev

# Store context
id_ = mesh.remember("prod DB is postgres 15 on AWS us-east-1")

# Search semantically
hits = mesh.query("what do we know about the database?")
for h in hits:
    print(h["score"], h["text"])

# Delete an entry
mesh.forget(id_)
```

## Async support

```python
from contextmesh import AsyncMesh

mesh = AsyncMesh("cm_live_your_key")
await mesh.remember("prod DB is postgres 15")
hits = await mesh.query("database info?")
```

## Links

- **Docs**: https://contextmesh.dev/docs
- **Dashboard**: https://contextmesh.dev/dashboard
- **GitHub**: https://github.com/contextmesh/contextmesh-mcp
