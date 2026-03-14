"""
ContextMesh — Persistent semantic memory for AI agents.

Quick start:
    from contextmesh import Mesh

    mesh = Mesh("cm_live_your_key")
    mesh.remember("prod DB is postgres 15 on AWS us-east-1")
    results = mesh.query("what do we know about the database?")
"""

from contextmesh._client import Mesh, AsyncMesh
from contextmesh._errors import ContextMeshError

__all__     = ["Mesh", "AsyncMesh", "ContextMeshError"]
__version__ = "1.0.0"
