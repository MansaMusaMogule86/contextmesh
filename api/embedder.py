"""
ContextMesh — Embedder
Converts text → 1536-dim vector using OpenAI ada-002.
Falls back to a lightweight local model if no OpenAI key.
"""

import os
import hashlib
import json
from pathlib import Path
from typing import Union
import httpx

OPENAI_KEY   = os.getenv("OPENAI_API_KEY", "")
CACHE_DIR    = Path(os.getenv("EMBED_CACHE_DIR", "/tmp/cm_embed_cache"))
EMBED_MODEL  = "text-embedding-ada-002"
EMBED_DIM    = 1536


class Embedder:
    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.use_openai = bool(OPENAI_KEY)

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return CACHE_DIR / f"{key}.json"

    def _read_cache(self, text: str) -> Union[list[float], None]:
        path = self._cache_path(self._cache_key(text))
        if path.exists():
            return json.loads(path.read_text())
        return None

    def _write_cache(self, text: str, vector: list[float]):
        path = self._cache_path(self._cache_key(text))
        path.write_text(json.dumps(vector))

    async def embed(self, text: str) -> list[float]:
        # Check cache first — saves API calls
        cached = self._read_cache(text)
        if cached:
            return cached

        if self.use_openai:
            vector = await self._embed_openai(text)
        else:
            vector = self._embed_fallback(text)

        self._write_cache(text, vector)
        return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Check which are cached
        results = []
        uncached_texts = []
        uncached_indices = []

        for i, text in enumerate(texts):
            cached = self._read_cache(text)
            if cached:
                results.append((i, cached))
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)

        if uncached_texts and self.use_openai:
            vectors = await self._embed_openai_batch(uncached_texts)
            for idx, vec in zip(uncached_indices, vectors):
                self._write_cache(texts[idx], vec)
                results.append((idx, vec))
        elif uncached_texts:
            for idx, text in zip(uncached_indices, uncached_texts):
                vec = self._embed_fallback(text)
                results.append((idx, vec))

        results.sort(key=lambda x: x[0])
        return [r[1] for r in results]

    async def _embed_openai(self, text: str) -> list[float]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                json={"input": text[:8191], "model": EMBED_MODEL},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]

    async def _embed_openai_batch(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                json={"input": [t[:8191] for t in texts], "model": EMBED_MODEL},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            data.sort(key=lambda x: x["index"])
            return [d["embedding"] for d in data]

    def _embed_fallback(self, text: str) -> list[float]:
        """
        Deterministic hash-based fallback when no OpenAI key.
        NOT semantically meaningful — for dev/testing only.
        In production, OpenAI key is required.
        """
        import struct, math
        h = hashlib.sha512(text.lower().encode()).digest()
        base = []
        for i in range(0, 64, 4):
            val = struct.unpack_from(">f", h, i)[0]
            if math.isfinite(val):
                base.append(val)
            else:
                base.append(float(i % 10) / 10.0)
        # Stretch to EMBED_DIM by cycling
        vec = [base[i % len(base)] * (1.0 + (i // len(base)) * 0.001) for i in range(EMBED_DIM)]
        # Normalise
        mag = sum(v*v for v in vec) ** 0.5
        return [v / mag for v in vec] if mag else vec
