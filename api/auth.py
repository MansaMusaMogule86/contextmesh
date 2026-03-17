"""
ContextMesh — Auth
API key validation, workspace resolution, plan limits.
Keys are stored in Redis: cm:key:{api_key} → JSON workspace config.
"""

import os
import json
import time
import hashlib
import secrets
from typing import Optional
from fastapi import Header, HTTPException, Depends
import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Plan limits
PLANS = {
    "free": {
        "queries_per_month":  1_000,
        "entries_max":        10_000,
        "workspaces":         1,
        "rate_per_minute":    20,
    },
    "solo": {
        "queries_per_month":  100_000,
        "entries_max":        500_000,
        "workspaces":         1,
        "rate_per_minute":    100,
    },
    "team": {
        "queries_per_month":  1_000_000,
        "entries_max":        5_000_000,
        "workspaces":         10,
        "rate_per_minute":    500,
    },
    "enterprise": {
        "queries_per_month":  -1,       # unlimited
        "entries_max":        -1,
        "workspaces":         -1,
        "rate_per_minute":    2000,
    },
}


class AuthManager:
    def __init__(self):
        self.r = redis.from_url(REDIS_URL, decode_responses=True)

    async def generate_key(self, workspace_id: str, plan: str = "free", label: str = "") -> str:
        raw     = secrets.token_urlsafe(32)
        api_key = f"cm_live_{raw}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        payload = {
            "workspace_id": workspace_id,
            "plan":         plan,
            "label":        label,
            "created_at":   int(time.time()),
            "active":       True,
        }
        await self.r.set(f"cm:key:{key_hash}", json.dumps(payload))
        await self.r.sadd(f"cm:workspace:{workspace_id}:keys", key_hash)
        return api_key

    async def validate(self, api_key: str) -> Optional[dict]:
        if not api_key or not api_key.startswith("cm_"):
            return None
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        raw = await self.r.get(f"cm:key:{key_hash}")
        if not raw:
            return None
        data = json.loads(raw)
        if not data.get("active"):
            return None
        return data

    async def check_rate_limit(self, workspace_id: str, plan: str) -> bool:
        limit = PLANS.get(plan, PLANS["free"])["rate_per_minute"]
        key   = f"cm:rate:{workspace_id}:{int(time.time() // 60)}"
        count = await self.r.incr(key)
        if count == 1:
            await self.r.expire(key, 120)
        return count <= limit

    async def check_query_limit(self, workspace_id: str, plan: str) -> bool:
        max_q = PLANS.get(plan, PLANS["free"])["queries_per_month"]
        if max_q == -1:
            return True
        month_key = f"cm:queries:{workspace_id}:{time.strftime('%Y-%m')}"
        count     = int(await self.r.get(month_key) or 0)
        return count < max_q

    async def increment_queries(self, workspace_id: str):
        month_key = f"cm:queries:{workspace_id}:{time.strftime('%Y-%m')}"
        await self.r.incr(month_key)
        # Auto-expire after 35 days
        await self.r.expire(month_key, 60 * 60 * 24 * 35)

    async def get_usage(self, workspace_id: str, plan: str) -> dict:
        month_key  = f"cm:queries:{workspace_id}:{time.strftime('%Y-%m')}"
        queries    = int(await self.r.get(month_key) or 0)
        plan_info  = PLANS.get(plan, PLANS["free"])
        return {
            "queries_used":        queries,
            "queries_limit":       plan_info["queries_per_month"],
            "entries_limit":       plan_info["entries_max"],
            "rate_limit_per_min":  plan_info["rate_per_minute"],
        }


# ── FastAPI dependency ──────────────────────────────────────────────────────

_auth = AuthManager()

async def require_auth(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key. Pass: Authorization: Bearer cm_live_...")
    api_key = authorization.removeprefix("Bearer ").strip()
    workspace = await _auth.validate(api_key)
    if not workspace:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key.")

    plan = workspace["plan"]
    wid  = workspace["workspace_id"]

    if not await _auth.check_rate_limit(wid, plan):
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded for {plan} plan. Upgrade at contextmesh.dev/billing")

    if not await _auth.check_query_limit(wid, plan):
        raise HTTPException(status_code=429, detail=f"Monthly query limit reached for {plan} plan. Upgrade at contextmesh.dev/billing")

    return workspace
