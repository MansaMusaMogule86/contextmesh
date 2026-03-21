"""
ContextMesh Python SDK
pip install contextmesh

Quick start:
    from contextmesh import Mesh
    mesh = Mesh("cm_live_your_key")
    mesh.remember("prod DB is postgres 15 on AWS us-east-1")
    results = mesh.query("what should I know about our database?")
"""

import httpx
import asyncio
from typing import Optional, Union


DEFAULT_BASE = "https://contextmesh.dev"


class ContextMeshError(Exception):
    pass


class Mesh:
    """
    Synchronous client. Works everywhere.
    For async usage, use AsyncMesh.
    """

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE):
        if not api_key:
            raise ContextMeshError("api_key is required. Get one at https://contextmesh.dev")
        self._key     = api_key
        self._base    = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        }

    def _post(self, path: str, body: dict) -> dict:
        with httpx.Client(timeout=15.0) as c:
            r = c.post(f"{self._base}{path}", headers=self._headers, json=body)
            self._raise(r)
            return r.json()

    def _get(self, path: str, params: dict = None) -> dict:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{self._base}{path}", headers=self._headers, params=params or {})
            self._raise(r)
            return r.json()

    def _delete(self, path: str) -> dict:
        with httpx.Client(timeout=15.0) as c:
            r = c.delete(f"{self._base}{path}", headers=self._headers)
            self._raise(r)
            return r.json()

    def _raise(self, r: httpx.Response):
        if r.status_code == 401:
            raise ContextMeshError("Invalid API key.")
        if r.status_code == 429:
            raise ContextMeshError(f"Rate/quota limit exceeded. {r.json().get('detail','')}")
        if r.status_code >= 400:
            raise ContextMeshError(f"API error {r.status_code}: {r.text}")

    def remember(
        self,
        text: str,
        tags: list[str] = None,
        source_agent: str = None,
        confidence: float = 1.0,
    ) -> str:
        """
        Store context. Returns the entry ID.

        mesh.remember("API rate limit is 1000 req/min per workspace")
        mesh.remember("Use camelCase for JS, snake_case for Python", tags=["conventions"])
        """
        result = self._post("/remember", {
            "text":         text,
            "tags":         tags or [],
            "source_agent": source_agent,
            "confidence":   confidence,
        })
        return result["id"]

    def query(
        self,
        q: str,
        top_k: int = 5,
        tag: str = None,
        min_score: float = 0.3,
    ) -> list[dict]:
        """
        Semantic search. Returns ranked list of context entries.

        results = mesh.query("what do we know about our database?")
        for r in results:
            print(r["text"], r["score"])
        """
        result = self._post("/query", {
            "q":          q,
            "top_k":      top_k,
            "tag_filter": tag,
            "min_score":  min_score,
        })
        return result["results"]

    def forget(self, entry_id: str) -> bool:
        """
        Delete a context entry by ID.
        """
        self._delete(f"/forget/{entry_id}")
        return True

    def list(self, limit: int = 50, offset: int = 0, tag: str = None) -> dict:
        """
        Browse stored entries.
        Returns {"total": int, "entries": [...]}
        """
        params = {"limit": limit, "offset": offset}
        if tag:
            params["tag_filter"] = tag
        return self._get("/list", params)

    def usage(self) -> dict:
        """
        Check plan usage for this month.
        """
        return self._get("/usage")

    # ── Convenience ──────────────────────────────────────────────────────────

    def remember_many(self, items: list[Union[str, dict]]) -> list[str]:
        """
        Bulk store. Pass strings or dicts with 'text', 'tags', etc.
        Returns list of IDs.
        """
        ids = []
        for item in items:
            if isinstance(item, str):
                ids.append(self.remember(item))
            else:
                ids.append(self.remember(**item))
        return ids

    def __repr__(self):
        return f"Mesh(key=...{self._key[-6:]}, base={self._base})"


class AsyncMesh:
    """
    Async client for use with asyncio / FastAPI / etc.
    """

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE):
        self._key     = api_key
        self._base    = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        }

    async def _post(self, path: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(f"{self._base}{path}", headers=self._headers, json=body)
            self._raise(r)
            return r.json()

    async def _get(self, path: str, params: dict = None) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(f"{self._base}{path}", headers=self._headers, params=params or {})
            self._raise(r)
            return r.json()

    async def _delete(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.delete(f"{self._base}{path}", headers=self._headers)
            self._raise(r)
            return r.json()

    def _raise(self, r: httpx.Response):
        if r.status_code == 401:
            raise ContextMeshError("Invalid API key.")
        if r.status_code == 429:
            raise ContextMeshError(f"Rate/quota limit exceeded. {r.json().get('detail','')}")
        if r.status_code >= 400:
            raise ContextMeshError(f"API error {r.status_code}: {r.text}")

    async def remember(self, text: str, tags: list[str] = None, source_agent: str = None, confidence: float = 1.0) -> str:
        result = await self._post("/remember", {"text": text, "tags": tags or [], "source_agent": source_agent, "confidence": confidence})
        return result["id"]

    async def query(self, q: str, top_k: int = 5, tag: str = None, min_score: float = 0.3) -> list[dict]:
        result = await self._post("/query", {"q": q, "top_k": top_k, "tag_filter": tag, "min_score": min_score})
        return result["results"]

    async def forget(self, entry_id: str) -> bool:
        await self._delete(f"/forget/{entry_id}")
        return True

    async def list(self, limit: int = 50, offset: int = 0, tag: str = None) -> dict:
        params = {"limit": limit, "offset": offset}
        if tag:
            params["tag_filter"] = tag
        return await self._get("/list", params)

    async def usage(self) -> dict:
        return await self._get("/usage")
