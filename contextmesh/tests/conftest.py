"""
Shared pytest fixtures for ContextMesh test suite.
Uses respx to mock all httpx calls — no real network needed.
"""

import pytest
import respx
import httpx
from unittest.mock import MagicMock, AsyncMock, patch

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api_key() -> str:
    return "cm_live_test_key_abc123"


@pytest.fixture
def base_url() -> str:
    return "https://api.contextmesh.dev"


@pytest.fixture
def mock_remember_response() -> dict:
    return {
        "id":     "e1a2b3c4-0000-0000-0000-000000000001",
        "status": "stored",
        "chars":  42,
        "tags":   ["database"],
    }


@pytest.fixture
def mock_query_response() -> dict:
    return {
        "query":   "what do we know about the database?",
        "count":   2,
        "results": [
            {
                "id":           "e1a2b3c4-0000-0000-0000-000000000001",
                "text":         "prod DB is postgres 15 on AWS us-east-1",
                "score":        0.9312,
                "tags":         ["database", "infra"],
                "source_agent": "cursor",
                "created_at":   1700000000,
            },
            {
                "id":           "e1a2b3c4-0000-0000-0000-000000000002",
                "text":         "Never run DROP TABLE without a migration file",
                "score":        0.7851,
                "tags":         ["database", "security"],
                "source_agent": "claude",
                "created_at":   1700001000,
            },
        ],
    }


@pytest.fixture
def mock_list_response() -> dict:
    return {
        "total":   2,
        "offset":  0,
        "limit":   50,
        "entries": [
            {"id": "e1", "text": "entry one", "tags": ["a"], "source_agent": "cursor", "created_at": 1700000000, "confidence": 1.0},
            {"id": "e2", "text": "entry two", "tags": ["b"], "source_agent": "claude", "created_at": 1700001000, "confidence": 0.9},
        ],
    }


@pytest.fixture
def mock_usage_response() -> dict:
    return {
        "workspace_id":   "ws_test123",
        "plan":           "team",
        "queries_used":   18400,
        "queries_limit":  1000000,
        "entries_stored": 42,
        "entries_limit":  5000000,
        "rate_limit_rpm": 500,
    }


# ── Vector store mock ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_qdrant():
    """Mock QdrantClient so vector_store tests don't need a real Qdrant."""
    with patch("qdrant_client.QdrantClient") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.get_collections.return_value.collections = []
        instance.upsert.return_value = None
        instance.search.return_value = []
        instance.scroll.return_value = ([], None)
        instance.get_collection.return_value.points_count = 0
        yield instance


@pytest.fixture
def mock_redis():
    """Mock redis.asyncio so auth tests don't need a real Redis."""
    with patch("redis.asyncio.from_url") as mock_fn:
        instance = AsyncMock()
        mock_fn.return_value = instance
        instance.get.return_value = None
        instance.set.return_value = True
        instance.incr.return_value = 1
        instance.expire.return_value = True
        instance.sadd.return_value = 1
        yield instance
