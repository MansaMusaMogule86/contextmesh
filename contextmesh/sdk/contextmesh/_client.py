"""
ContextMesh Python client.

Sync:  Mesh("cm_live_key")
Async: AsyncMesh("cm_live_key")
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing  import Any, Optional, Union

import httpx

from contextmesh._errors import AuthError, RateLimitError, NotFoundError, APIError

DEFAULT_BASE = "https://api.contextmesh.dev"
TIMEOUT      = httpx.Timeout(15.0)


def _build_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _raise_for_status(r: httpx.Response) -> None:
    if r.status_code == 401:
        raise AuthError("Invalid or revoked API key.", 401)
    if r.status_code == 404:
        raise NotFoundError(r.json().get("detail", "Not found."), 404)
    if r.status_code == 429:
        raise RateLimitError(r.json().get("detail", "Rate/quota limit exceeded."), 429)
    if r.status_code >= 400:
        raise APIError(f"API error {r.status_code}: {r.text}", r.status_code)


# ── Sync client ───────────────────────────────────────────────────────────────

class Mesh:
    """
    Synchronous ContextMesh client.

    Example::

        from contextmesh import Mesh

        mesh = Mesh("cm_live_your_key")
        id_  = mesh.remember("prod DB is postgres 15 on AWS us-east-1")
        hits = mesh.query("what do we know about the database?")
        for h in hits:
            print(h["score"], h["text"])
    """

    def __init__(
        self,
        api_key:  str,
        base_url: str = DEFAULT_BASE,
        timeout:  float = 15.0,
    ) -> None:
        if not api_key:
            raise AuthError("api_key is required. Get one at https://contextmesh.dev")
        self._key     = api_key
        self._base    = base_url.rstrip("/")
        self._headers = _build_headers(api_key)
        self._timeout = httpx.Timeout(timeout)

    # ── Core endpoints ────────────────────────────────────────────────────────

    def remember(
        self,
        text:         str,
        tags:         list[str]      = None,
        source_agent: Optional[str]  = None,
        confidence:   float          = 1.0,
    ) -> str:
        """
        Store a piece of context. Returns the entry ID.

        Args:
            text:         The context to remember.
            tags:         Optional list of tags for filtering later.
            source_agent: Which agent wrote this (e.g. "cursor", "claude").
            confidence:   How confident you are in this (0.0–1.0).

        Returns:
            str: Entry ID — use it later to delete this entry.
        """
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(
                f"{self._base}/remember",
                headers=self._headers,
                json={"text": text, "tags": tags or [], "source_agent": source_agent, "confidence": confidence},
            )
            _raise_for_status(r)
            return r.json()["id"]

    def query(
        self,
        q:         str,
        top_k:     int           = 5,
        tag:       Optional[str] = None,
        min_score: float         = 0.3,
    ) -> list[dict[str, Any]]:
        """
        Semantic search over stored context.

        Args:
            q:         Natural language query.
            top_k:     Max results to return (1–20).
            tag:       Only return entries with this tag.
            min_score: Minimum similarity score (0.0–1.0).

        Returns:
            List of dicts: [{id, text, score, tags, source_agent, created_at}, ...]
        """
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(
                f"{self._base}/query",
                headers=self._headers,
                json={"q": q, "top_k": top_k, "tag_filter": tag, "min_score": min_score},
            )
            _raise_for_status(r)
            return r.json()["results"]

    def forget(self, entry_id: str) -> bool:
        """Delete a context entry by ID."""
        with httpx.Client(timeout=self._timeout) as c:
            r = c.delete(f"{self._base}/forget/{entry_id}", headers=self._headers)
            _raise_for_status(r)
            return True

    def list(
        self,
        limit:  int           = 50,
        offset: int           = 0,
        tag:    Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Browse stored entries.

        Returns:
            {total: int, entries: [...], offset: int, limit: int}
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if tag:
            params["tag_filter"] = tag
        with httpx.Client(timeout=self._timeout) as c:
            r = c.get(f"{self._base}/list", headers=self._headers, params=params)
            _raise_for_status(r)
            return r.json()

    def usage(self) -> dict[str, Any]:
        """Check this month's plan usage."""
        with httpx.Client(timeout=self._timeout) as c:
            r = c.get(f"{self._base}/usage", headers=self._headers)
            _raise_for_status(r)
            return r.json()

    # ── Convenience ───────────────────────────────────────────────────────────

    def remember_many(
        self,
        items: list[Union[str, dict[str, Any]]],
    ) -> list[str]:
        """Bulk store. Pass strings or dicts with text/tags/confidence keys."""
        ids = []
        for item in items:
            if isinstance(item, str):
                ids.append(self.remember(item))
            else:
                ids.append(self.remember(**item))
        return ids

    def __repr__(self) -> str:
        return f"Mesh(key=...{self._key[-6:]}, base={self._base})"


# ── Async client ──────────────────────────────────────────────────────────────

class AsyncMesh:
    """
    Async ContextMesh client for use with asyncio / FastAPI / etc.

    Example::

        from contextmesh import AsyncMesh

        mesh = AsyncMesh("cm_live_your_key")
        await mesh.remember("prod DB is postgres 15")
        hits = await mesh.query("database info?")
    """

    def __init__(
        self,
        api_key:  str,
        base_url: str   = DEFAULT_BASE,
        timeout:  float = 15.0,
    ) -> None:
        if not api_key:
            raise AuthError("api_key is required.")
        self._key     = api_key
        self._base    = base_url.rstrip("/")
        self._headers = _build_headers(api_key)
        self._timeout = httpx.Timeout(timeout)

    async def remember(
        self,
        text:         str,
        tags:         list[str]     = None,
        source_agent: Optional[str] = None,
        confidence:   float         = 1.0,
    ) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.post(
                f"{self._base}/remember",
                headers=self._headers,
                json={"text": text, "tags": tags or [], "source_agent": source_agent, "confidence": confidence},
            )
            _raise_for_status(r)
            return r.json()["id"]

    async def query(
        self,
        q:         str,
        top_k:     int           = 5,
        tag:       Optional[str] = None,
        min_score: float         = 0.3,
    ) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.post(
                f"{self._base}/query",
                headers=self._headers,
                json={"q": q, "top_k": top_k, "tag_filter": tag, "min_score": min_score},
            )
            _raise_for_status(r)
            return r.json()["results"]

    async def forget(self, entry_id: str) -> bool:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.delete(f"{self._base}/forget/{entry_id}", headers=self._headers)
            _raise_for_status(r)
            return True

    async def list(
        self,
        limit:  int           = 50,
        offset: int           = 0,
        tag:    Optional[str] = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if tag:
            params["tag_filter"] = tag
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.get(f"{self._base}/list", headers=self._headers, params=params)
            _raise_for_status(r)
            return r.json()

    async def usage(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.get(f"{self._base}/usage", headers=self._headers)
            _raise_for_status(r)
            return r.json()

    async def remember_many(
        self,
        items: list[Union[str, dict[str, Any]]],
    ) -> list[str]:
        import asyncio
        return list(await asyncio.gather(*[
            self.remember(i) if isinstance(i, str) else self.remember(**i)
            for i in items
        ]))

    def __repr__(self) -> str:
        return f"AsyncMesh(key=...{self._key[-6:]}, base={self._base})"
