"""
Tests for the ContextMesh Python SDK (Mesh + AsyncMesh).
All HTTP calls are mocked via respx — no network required.
"""

import pytest
import respx
import httpx
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

from contextmesh import Mesh, AsyncMesh, ContextMeshError
from contextmesh._errors import AuthError, RateLimitError, NotFoundError

BASE = "https://api.contextmesh.dev"


# ── Mesh (sync) ───────────────────────────────────────────────────────────────

class TestMeshInit:
    def test_requires_api_key(self):
        with pytest.raises(AuthError):
            Mesh("")

    def test_repr_masks_key(self, api_key):
        m = Mesh(api_key)
        assert "cm_live" not in repr(m)
        assert api_key[-6:] in repr(m)

    def test_custom_base_url(self, api_key):
        m = Mesh(api_key, base_url="http://localhost:8000")
        assert "localhost" in repr(m)


class TestMeshRemember:
    @respx.mock
    def test_remember_returns_id(self, api_key, mock_remember_response):
        respx.post(f"{BASE}/remember").mock(
            return_value=httpx.Response(200, json=mock_remember_response)
        )
        mesh = Mesh(api_key)
        entry_id = mesh.remember("prod DB is postgres 15")
        assert entry_id == mock_remember_response["id"]

    @respx.mock
    def test_remember_sends_tags(self, api_key, mock_remember_response):
        route = respx.post(f"{BASE}/remember").mock(
            return_value=httpx.Response(200, json=mock_remember_response)
        )
        Mesh(api_key).remember("test", tags=["database", "infra"])
        body = route.calls[0].request.content
        import json
        assert json.loads(body)["tags"] == ["database", "infra"]

    @respx.mock
    def test_remember_sends_confidence(self, api_key, mock_remember_response):
        route = respx.post(f"{BASE}/remember").mock(
            return_value=httpx.Response(200, json=mock_remember_response)
        )
        Mesh(api_key).remember("test", confidence=0.75)
        import json
        body = json.loads(route.calls[0].request.content)
        assert body["confidence"] == 0.75

    @respx.mock
    def test_remember_401_raises_auth_error(self, api_key):
        respx.post(f"{BASE}/remember").mock(
            return_value=httpx.Response(401, json={"detail": "Invalid key"})
        )
        with pytest.raises(AuthError):
            Mesh(api_key).remember("test")

    @respx.mock
    def test_remember_429_raises_rate_limit(self, api_key):
        respx.post(f"{BASE}/remember").mock(
            return_value=httpx.Response(429, json={"detail": "Quota exceeded"})
        )
        with pytest.raises(RateLimitError):
            Mesh(api_key).remember("test")


class TestMeshQuery:
    @respx.mock
    def test_query_returns_results(self, api_key, mock_query_response):
        respx.post(f"{BASE}/query").mock(
            return_value=httpx.Response(200, json=mock_query_response)
        )
        results = Mesh(api_key).query("database?")
        assert len(results) == 2
        assert results[0]["score"] == 0.9312
        assert results[0]["text"]  == "prod DB is postgres 15 on AWS us-east-1"

    @respx.mock
    def test_query_sends_top_k(self, api_key, mock_query_response):
        route = respx.post(f"{BASE}/query").mock(
            return_value=httpx.Response(200, json=mock_query_response)
        )
        Mesh(api_key).query("test", top_k=10)
        import json
        assert json.loads(route.calls[0].request.content)["top_k"] == 10

    @respx.mock
    def test_query_sends_tag_filter(self, api_key, mock_query_response):
        route = respx.post(f"{BASE}/query").mock(
            return_value=httpx.Response(200, json=mock_query_response)
        )
        Mesh(api_key).query("test", tag="database")
        import json
        assert json.loads(route.calls[0].request.content)["tag_filter"] == "database"

    @respx.mock
    def test_query_empty_results(self, api_key):
        respx.post(f"{BASE}/query").mock(
            return_value=httpx.Response(200, json={"query":"x","count":0,"results":[]})
        )
        results = Mesh(api_key).query("nothing matches")
        assert results == []


class TestMeshForget:
    @respx.mock
    def test_forget_returns_true(self, api_key):
        respx.delete(f"{BASE}/forget/e1a2b3c4").mock(
            return_value=httpx.Response(200, json={"id": "e1a2b3c4", "status": "deleted"})
        )
        result = Mesh(api_key).forget("e1a2b3c4")
        assert result is True

    @respx.mock
    def test_forget_404_raises_not_found(self, api_key):
        respx.delete(f"{BASE}/forget/bad-id").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )
        with pytest.raises(NotFoundError):
            Mesh(api_key).forget("bad-id")


class TestMeshList:
    @respx.mock
    def test_list_returns_entries(self, api_key, mock_list_response):
        respx.get(f"{BASE}/list").mock(
            return_value=httpx.Response(200, json=mock_list_response)
        )
        result = Mesh(api_key).list()
        assert result["total"] == 2
        assert len(result["entries"]) == 2

    @respx.mock
    def test_list_with_tag(self, api_key, mock_list_response):
        route = respx.get(f"{BASE}/list").mock(
            return_value=httpx.Response(200, json=mock_list_response)
        )
        Mesh(api_key).list(tag="database")
        assert "tag_filter=database" in str(route.calls[0].request.url)


class TestMeshUsage:
    @respx.mock
    def test_usage_returns_plan_info(self, api_key, mock_usage_response):
        respx.get(f"{BASE}/usage").mock(
            return_value=httpx.Response(200, json=mock_usage_response)
        )
        usage = Mesh(api_key).usage()
        assert usage["plan"] == "team"
        assert usage["queries_used"] == 18400


class TestMeshRememberMany:
    @respx.mock
    def test_remember_many_strings(self, api_key, mock_remember_response):
        respx.post(f"{BASE}/remember").mock(
            return_value=httpx.Response(200, json=mock_remember_response)
        )
        ids = Mesh(api_key).remember_many(["entry one", "entry two"])
        assert len(ids) == 2

    @respx.mock
    def test_remember_many_dicts(self, api_key, mock_remember_response):
        respx.post(f"{BASE}/remember").mock(
            return_value=httpx.Response(200, json=mock_remember_response)
        )
        ids = Mesh(api_key).remember_many([
            {"text": "entry one", "tags": ["a"]},
            {"text": "entry two", "tags": ["b"]},
        ])
        assert len(ids) == 2


# ── AsyncMesh ─────────────────────────────────────────────────────────────────

class TestAsyncMesh:
    @respx.mock
    @pytest.mark.asyncio
    async def test_async_remember(self, api_key, mock_remember_response):
        respx.post(f"{BASE}/remember").mock(
            return_value=httpx.Response(200, json=mock_remember_response)
        )
        mesh = AsyncMesh(api_key)
        entry_id = await mesh.remember("prod DB is postgres 15")
        assert entry_id == mock_remember_response["id"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_query(self, api_key, mock_query_response):
        respx.post(f"{BASE}/query").mock(
            return_value=httpx.Response(200, json=mock_query_response)
        )
        results = await AsyncMesh(api_key).query("database?")
        assert len(results) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_forget(self, api_key):
        respx.delete(f"{BASE}/forget/e1").mock(
            return_value=httpx.Response(200, json={"id":"e1","status":"deleted"})
        )
        result = await AsyncMesh(api_key).forget("e1")
        assert result is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_remember_many_concurrent(self, api_key, mock_remember_response):
        respx.post(f"{BASE}/remember").mock(
            return_value=httpx.Response(200, json=mock_remember_response)
        )
        ids = await AsyncMesh(api_key).remember_many(["a", "b", "c"])
        assert len(ids) == 3

    @pytest.mark.asyncio
    async def test_async_requires_key(self):
        with pytest.raises(AuthError):
            AsyncMesh("")
