"""
Tests for VectorStore — mocked Qdrant, no real server needed.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

WORKSPACE = "ws_test"
MOCK_VEC  = [0.01] * 1536


def make_store(mock_qdrant):
    with patch("qdrant_client.QdrantClient", return_value=mock_qdrant):
        from vector_store import VectorStore
        return VectorStore()


class TestVectorStoreWrite:
    def test_write_returns_uuid(self, mock_qdrant):
        store = make_store(mock_qdrant)
        entry_id = store.write(WORKSPACE, "test context", MOCK_VEC)
        assert isinstance(entry_id, str)
        assert len(entry_id) == 36   # UUID format

    def test_write_calls_upsert(self, mock_qdrant):
        store = make_store(mock_qdrant)
        store.write(WORKSPACE, "test context", MOCK_VEC, tags=["database"])
        mock_qdrant.upsert.assert_called_once()

    def test_write_includes_metadata(self, mock_qdrant):
        store = make_store(mock_qdrant)
        store.write(WORKSPACE, "test context", MOCK_VEC,
                    tags=["a", "b"], source_agent="cursor", confidence=0.85)
        call_args = mock_qdrant.upsert.call_args
        point = call_args.kwargs["points"][0]
        assert point.payload["tags"]         == ["a", "b"]
        assert point.payload["source_agent"] == "cursor"
        assert point.payload["confidence"]   == 0.85
        assert point.payload["text"]         == "test context"

    def test_write_creates_collection_if_missing(self, mock_qdrant):
        mock_qdrant.get_collections.return_value.collections = []
        store = make_store(mock_qdrant)
        store.write(WORKSPACE, "test", MOCK_VEC)
        mock_qdrant.create_collection.assert_called_once()

    def test_write_skips_collection_if_exists(self, mock_qdrant):
        existing = MagicMock()
        existing.name = f"cm_{WORKSPACE}"
        mock_qdrant.get_collections.return_value.collections = [existing]
        store = make_store(mock_qdrant)
        store.write(WORKSPACE, "test", MOCK_VEC)
        mock_qdrant.create_collection.assert_not_called()


class TestVectorStoreQuery:
    def test_query_maps_results(self, mock_qdrant):
        hit = MagicMock()
        hit.id      = "e-id-001"
        hit.score   = 0.92
        hit.payload = {
            "text": "postgres 15 on AWS", "tags": ["db"],
            "source_agent": "cursor", "created_at": 1700000000
        }
        mock_qdrant.search.return_value = [hit]

        store = make_store(mock_qdrant)
        results = store.query(WORKSPACE, MOCK_VEC, top_k=5)

        assert len(results) == 1
        assert results[0]["id"]    == "e-id-001"
        assert results[0]["score"] == 0.92
        assert results[0]["text"]  == "postgres 15 on AWS"

    def test_query_empty_results(self, mock_qdrant):
        mock_qdrant.search.return_value = []
        store = make_store(mock_qdrant)
        results = store.query(WORKSPACE, MOCK_VEC)
        assert results == []


class TestVectorStoreForget:
    def test_forget_returns_true_on_success(self, mock_qdrant):
        store = make_store(mock_qdrant)
        result = store.forget(WORKSPACE, "e-id-001")
        assert result is True
        mock_qdrant.delete.assert_called_once()

    def test_forget_returns_false_on_error(self, mock_qdrant):
        mock_qdrant.delete.side_effect = Exception("not found")
        store = make_store(mock_qdrant)
        result = store.forget(WORKSPACE, "bad-id")
        assert result is False


class TestVectorStoreStats:
    def test_stats_returns_count(self, mock_qdrant):
        mock_qdrant.get_collection.return_value.points_count = 42
        store = make_store(mock_qdrant)
        stats = store.stats(WORKSPACE)
        assert stats["total_entries"] == 42
        assert "collection" in stats

    def test_count_returns_zero_on_error(self, mock_qdrant):
        mock_qdrant.get_collection.side_effect = Exception("not found")
        store = make_store(mock_qdrant)
        assert store.count(WORKSPACE) == 0
