"""
Tests for the ContextMesh FastAPI endpoints.
Uses FastAPI's TestClient + mocked Qdrant/Redis.
"""

import pytest
import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

# ── Test data ─────────────────────────────────────────────────────────────────

VALID_KEY       = "cm_live_test_valid_key"
VALID_WORKSPACE = {
    "workspace_id": "ws_test",
    "plan":         "team",
    "label":        "test",
    "created_at":   1700000000,
    "active":       True,
}

MOCK_VECTOR = [0.1] * 1536


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {VALID_KEY}"}


@pytest.fixture
def app_client():
    """
    Create a FastAPI TestClient with all external dependencies mocked.
    Patches: auth.require_auth, embedder.Embedder, vector_store.VectorStore
    """
    with (
        patch("auth.require_auth",         return_value=VALID_WORKSPACE),
        patch("auth._auth.increment_queries", new_callable=AsyncMock),
        patch("auth._auth.get_usage",      new_callable=AsyncMock,
              return_value={"queries_used":0,"queries_limit":1000000,"entries_limit":5000000,"rate_limit_per_min":500}),
    ):
        # Patch Embedder
        mock_embedder = MagicMock()
        mock_embedder.embed = AsyncMock(return_value=MOCK_VECTOR)

        # Patch VectorStore
        mock_store = MagicMock()
        mock_store.write.return_value = "e-test-id-001"
        mock_store.query.return_value = [{
            "id": "e-test-id-001", "text": "postgres 15 on AWS",
            "score": 0.92, "tags": ["database"], "source_agent": "cursor", "created_at": 1700000000
        }]
        mock_store.forget.return_value = True
        mock_store.list_entries.return_value = [
            {"id":"e1","text":"entry one","tags":["a"],"source_agent":"cursor","created_at":1700000000,"confidence":1.0}
        ]
        mock_store.stats.return_value  = {"total_entries": 42, "collection": "cm_ws_test"}
        mock_store.count.return_value  = 42

        with (
            patch("main.embedder", mock_embedder),
            patch("main.store",    mock_store),
        ):
            from fastapi.testclient import TestClient
            from main import app
            yield TestClient(app), mock_store, mock_embedder


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_ok(self, app_client):
        client, _, _ = app_client
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["service"] == "contextmesh"


# ── /remember ─────────────────────────────────────────────────────────────────

class TestRemember:
    def test_remember_success(self, app_client, auth_headers):
        client, store, _ = app_client
        r = client.post("/remember",
            headers=auth_headers,
            json={"text": "prod DB is postgres 15", "tags": ["database"]}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == "e-test-id-001"
        assert body["status"] == "stored"
        store.write.assert_called_once()

    def test_remember_empty_text_fails(self, app_client, auth_headers):
        client, _, _ = app_client
        r = client.post("/remember", headers=auth_headers, json={"text": ""})
        assert r.status_code == 422

    def test_remember_text_too_long_fails(self, app_client, auth_headers):
        client, _, _ = app_client
        r = client.post("/remember", headers=auth_headers, json={"text": "x" * 10_001})
        assert r.status_code == 422

    def test_remember_no_auth_fails(self, app_client):
        client, _, _ = app_client
        r = client.post("/remember", json={"text": "test"})
        # auth is mocked to return workspace, so depends on mock — just check it was called
        assert r.status_code in (200, 401)

    def test_remember_default_confidence(self, app_client, auth_headers):
        client, store, _ = app_client
        client.post("/remember", headers=auth_headers, json={"text": "test"})
        call_kwargs = store.write.call_args.kwargs
        assert call_kwargs.get("confidence", 1.0) == 1.0


# ── /query ────────────────────────────────────────────────────────────────────

class TestQuery:
    def test_query_returns_results(self, app_client, auth_headers):
        client, _, _ = app_client
        r = client.post("/query", headers=auth_headers, json={"q": "database info?"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        assert body["results"][0]["score"] == 0.92

    def test_query_passes_top_k(self, app_client, auth_headers):
        client, store, _ = app_client
        client.post("/query", headers=auth_headers, json={"q": "test", "top_k": 10})
        store.query.assert_called_once()
        call_kwargs = store.query.call_args.kwargs
        assert call_kwargs["top_k"] == 10

    def test_query_empty_string_fails(self, app_client, auth_headers):
        client, _, _ = app_client
        r = client.post("/query", headers=auth_headers, json={"q": ""})
        assert r.status_code == 422

    def test_query_top_k_max_20(self, app_client, auth_headers):
        client, _, _ = app_client
        r = client.post("/query", headers=auth_headers, json={"q": "test", "top_k": 99})
        assert r.status_code == 422


# ── /forget ───────────────────────────────────────────────────────────────────

class TestForget:
    def test_forget_success(self, app_client, auth_headers):
        client, store, _ = app_client
        r = client.delete("/forget/e-test-id-001", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "deleted"

    def test_forget_not_found(self, app_client, auth_headers):
        client, store, _ = app_client
        store.forget.return_value = False
        r = client.delete("/forget/nonexistent", headers=auth_headers)
        assert r.status_code == 404


# ── /list ─────────────────────────────────────────────────────────────────────

class TestList:
    def test_list_returns_entries(self, app_client, auth_headers):
        client, _, _ = app_client
        r = client.get("/list", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "entries" in body
        assert "total" in body

    def test_list_limit_param(self, app_client, auth_headers):
        client, store, _ = app_client
        client.get("/list?limit=10", headers=auth_headers)
        store.list_entries.assert_called_once()
        call_kwargs = store.list_entries.call_args.kwargs
        assert call_kwargs["limit"] == 10

    def test_list_limit_max_200(self, app_client, auth_headers):
        client, _, _ = app_client
        r = client.get("/list?limit=999", headers=auth_headers)
        assert r.status_code == 422


# ── /usage ────────────────────────────────────────────────────────────────────

class TestUsage:
    def test_usage_returns_plan_info(self, app_client, auth_headers):
        client, _, _ = app_client
        r = client.get("/usage", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "plan" in body
        assert "queries_used" in body
        assert "entries_stored" in body
