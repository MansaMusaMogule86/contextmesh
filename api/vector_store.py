"""
ContextMesh — Vector Store
Wraps Qdrant for semantic context storage and retrieval.
One collection per workspace. Namespaced, fast, queryable.
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
    SearchRequest, ScoredPoint
)
from typing import Optional
import uuid
import time
import os

VECTOR_SIZE = 1536  # OpenAI ada-002
QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_KEY  = os.getenv("QDRANT_API_KEY", "")


class VectorStore:
    def __init__(self):
        kwargs = {"url": QDRANT_URL}
        if QDRANT_KEY:
            kwargs["api_key"] = QDRANT_KEY
        self.client = QdrantClient(**kwargs)

    def _collection(self, workspace_id: str) -> str:
        # Each workspace gets its own Qdrant collection
        return f"cm_{workspace_id}"

    def ensure_collection(self, workspace_id: str):
        name = self._collection(workspace_id)
        existing = [c.name for c in self.client.get_collections().collections]
        if name not in existing:
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )

    def write(
        self,
        workspace_id: str,
        text: str,
        vector: list[float],
        tags: list[str] = None,
        source_agent: str = None,
        confidence: float = 1.0,
    ) -> str:
        self.ensure_collection(workspace_id)
        entry_id = str(uuid.uuid4())
        self.client.upsert(
            collection_name=self._collection(workspace_id),
            points=[PointStruct(
                id=entry_id,
                vector=vector,
                payload={
                    "text":         text,
                    "tags":         tags or [],
                    "source_agent": source_agent or "unknown",
                    "confidence":   confidence,
                    "created_at":   int(time.time()),
                    "workspace_id": workspace_id,
                }
            )]
        )
        return entry_id

    def query(
        self,
        workspace_id: str,
        query_vector: list[float],
        top_k: int = 5,
        tag_filter: Optional[str] = None,
        min_score: float = 0.3,
    ) -> list[dict]:
        self.ensure_collection(workspace_id)

        query_filter = None
        if tag_filter:
            query_filter = Filter(
                must=[FieldCondition(key="tags", match=MatchValue(value=tag_filter))]
            )

        results: list[ScoredPoint] = self.client.search(
            collection_name=self._collection(workspace_id),
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
            score_threshold=min_score,
            with_payload=True,
        )

        return [
            {
                "id":           r.id,
                "text":         r.payload["text"],
                "score":        round(r.score, 4),
                "tags":         r.payload.get("tags", []),
                "source_agent": r.payload.get("source_agent"),
                "created_at":   r.payload.get("created_at"),
            }
            for r in results
        ]

    def forget(self, workspace_id: str, entry_id: str) -> bool:
        try:
            self.client.delete(
                collection_name=self._collection(workspace_id),
                points_selector=[entry_id],
            )
            return True
        except Exception:
            return False

    def list_entries(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
        tag_filter: Optional[str] = None,
    ) -> list[dict]:
        self.ensure_collection(workspace_id)

        scroll_filter = None
        if tag_filter:
            scroll_filter = Filter(
                must=[FieldCondition(key="tags", match=MatchValue(value=tag_filter))]
            )

        results, _ = self.client.scroll(
            collection_name=self._collection(workspace_id),
            scroll_filter=scroll_filter,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        return [
            {
                "id":           r.id,
                "text":         r.payload["text"],
                "tags":         r.payload.get("tags", []),
                "source_agent": r.payload.get("source_agent"),
                "created_at":   r.payload.get("created_at"),
                "confidence":   r.payload.get("confidence", 1.0),
            }
            for r in results
        ]

    def count(self, workspace_id: str) -> int:
        try:
            info = self.client.get_collection(self._collection(workspace_id))
            return info.points_count
        except Exception:
            return 0

    def stats(self, workspace_id: str) -> dict:
        return {
            "total_entries": self.count(workspace_id),
            "collection":    self._collection(workspace_id),
        }
