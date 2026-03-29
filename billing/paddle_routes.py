"""
ContextMesh — Paddle Billing Routes
Replaces Stripe. Paddle handles VAT, tax, Apple Pay globally.
UAE-friendly, no US entity required.

Endpoints:
  GET  /billing/plans           → List plans + pricing
  POST /billing/checkout        → Create Paddle checkout URL
  POST /billing/webhook         → Handle Paddle webhook events
  GET  /billing/success         → Post-checkout landing

Flow:
  1. User picks plan → POST /billing/checkout
  2. Redirected to Paddle-hosted checkout (Apple Pay, card, etc.)
  3. On success → Paddle fires subscription.activated webhook
  4. Webhook: generate API key → email to user via Resend
  5. User is live
"""

import os
import json
import time
import hmac
import hashlib
import secrets
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel

log = logging.getLogger("contextmesh.billing")

router = APIRouter(prefix="/billing", tags=["billing"])

# ── Config ────────────────────────────────────────────────────────────────────

PADDLE_API_KEY       = os.getenv("PADDLE_API_KEY", "")
PADDLE_WEBHOOK_SECRET = os.getenv("PADDLE_WEBHOOK_SECRET", "")
PADDLE_BASE          = "https://api.paddle.com"   # sandbox: api.sandbox.paddle.com
APP_URL              = os.getenv("APP_URL", "https://contextmesh.dev")
API_URL              = os.getenv("API_URL", "https://contextmesh.dev")
RESEND_API_KEY       = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL           = os.getenv("FROM_EMAIL", "keys@contextmesh.dev")

# Paddle Price IDs — create in Paddle dashboard → Catalog → Products
# Then set these env vars
PRICE_IDS = {
    "solo":       os.getenv("PADDLE_PRICE_SOLO",       ""),
    "team":       os.getenv("PADDLE_PRICE_TEAM",       ""),
    "enterprise": os.getenv("PADDLE_PRICE_ENTERPRISE", ""),
}

PLAN_DETAILS = {
    "free": {
        "name": "Free", "price_monthly": 0,
        "queries_limit": 1_000, "entries_limit": 10_000,
        "rate_limit_per_min": 20, "workspaces": 1,
    },
    "solo": {
        "name": "Solo", "price_monthly": 19,
        "queries_limit": 100_000, "entries_limit": 500_000,
        "rate_limit_per_min": 100, "workspaces": 1,
    },
    "team": {
        "name": "Team", "price_monthly": 99,
        "queries_limit": 1_000_000, "entries_limit": 5_000_000,
        "rate_limit_per_min": 500, "workspaces": 10,
    },
    "enterprise": {
        "name": "Enterprise", "price_monthly": 599,
        "queries_limit": -1, "entries_limit": -1,
        "rate_limit_per_min": 2000, "workspaces": -1,
    },
}

# ── Paddle API helper ─────────────────────────────────────────────────────────

def paddle_headers() -> dict:
    if not PADDLE_API_KEY:
        raise HTTPException(500, "PADDLE_API_KEY not configured")
    return {
        "Authorization": f"Bearer {PADDLE_API_KEY}",
        "Content-Type":  "application/json",
    }


async def paddle_post(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{PADDLE_BASE}{path}", headers=paddle_headers(), json=body)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, f"Paddle error: {r.text}")
        return r.json()


async def paddle_get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{PADDLE_BASE}{path}", headers=paddle_headers())
        if r.status_code >= 400:
            raise HTTPException(r.status_code, f"Paddle error: {r.text}")
        return r.json()

# ── Key generation ────────────────────────────────────────────────────────────

def generate_api_key() -> str:
    return f"cm_live_{secrets.token_urlsafe(32)}"


async def provision_and_email(email: str, plan: str, workspace_id: str, redis=None):
    """Generate API key, store in Redis, email to user."""
    api_key  = generate_api_key()
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    workspace_data = json.dumps({
        "workspace_id": workspace_id,
        "plan":         plan,
        "label":        workspace_id,
        "created_at":   int(time.time()),
        "active":       True,
    })

    if redis:
        await redis.set(f"cm:key:{key_hash}", workspace_data, ex=60*60*24*365)
        log.info("Provisioned workspace %s plan=%s", workspace_id, plan)
    else:
        log.warning("No Redis — key not persisted: %s", api_key)

    await send_key_email(email, api_key, plan, workspace_id)
    return api_key


async def send_key_email(email: str, api_key: str, plan: str, workspace_id: str):
    if not RESEND_API_KEY:
        log.warning("RESEND_API_KEY not set — skipping email to %s", email)
        log.info("KEY for %s: %s", email, api_key)
        return

    html = f"""
    <div style="font-family:monospace;max-width:520px;margin:0 auto;padding:40px 20px;background:#0A0A08;color:#F2EFE8;">
      <div style="font-size:22px;font-weight:600;margin-bottom:24px;">◈ Your ContextMesh API Key</div>
      <p style="color:#A0A099;margin-bottom:16px;">
        You're on the <strong style="color:#C8FF00;">{plan.upper()}</strong> plan.
        Workspace: <code style="color:#C8FF00;">{workspace_id}</code>
      </p>
      <div style="background:#141414;border:1px solid #2A2A2A;border-radius:6px;padding:16px;margin:20px 0;">
        <div style="font-size:11px;color:#5A5A52;margin-bottom:8px;letter-spacing:0.1em;text-transform:uppercase;">API Key — Save this, we can't recover it</div>
        <div style="font-size:14px;color:#C8FF00;word-break:break-all;">{api_key}</div>
      </div>
      <div style="background:#141414;border:1px solid #2A2A2A;border-radius:6px;padding:14px;font-size:12px;color:#A0A099;margin-top:20px;">
        pip install contextmesh<br><br>
        from contextmesh import Mesh<br>
        mesh = Mesh("{api_key[:24]}...")<br>
        mesh.remember("your first context")
      </div>
      <div style="margin-top:24px;">
        <a href="https://contextmesh.dev/docs" style="color:#C8FF00;font-size:13px;">Docs →</a>
        &nbsp;&nbsp;
        <a href="{APP_URL}/dashboard" style="color:#C8FF00;font-size:13px;">Dashboard →</a>
      </div>
    </div>
    """

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": FROM_EMAIL, "to": [email], "subject": f"Your ContextMesh API key ({plan} plan)", "html": html},
        )
        if r.status_code >= 400:
            log.error("Email failed: %s %s", r.status_code, r.text)
        else:
            log.info("Key emailed to %s", email)

# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/plans")
async def list_plans():
    return {
        "plans": [
            {
                "id":         plan_id,
                "name":       info["name"],
                "price_usd":  info["price_monthly"],
                "queries_mo": info["queries_limit"],
                "entries":    info["entries_limit"],
                "rate_rpm":   info["rate_limit_per_min"],
                "workspaces": info["workspaces"],
            }
            for plan_id, info in PLAN_DETAILS.items()
        ]
    }


class CheckoutRequest(BaseModel):
    plan:  str
    email: str


@router.post("/checkout")
async def create_checkout(body: CheckoutRequest):
    plan = body.plan.lower()

    # Free plan — provision instantly, no payment
    if plan == "free":
        workspace_id = f"ws_{secrets.token_hex(8)}"
        from auth import _auth
        api_key = await _auth.generate_key(workspace_id=workspace_id, plan="free", label=body.email)
        await send_key_email(body.email, api_key, "free", workspace_id)
        return {
            "plan":         "free",
            "workspace_id": workspace_id,
            "api_key":      api_key,
            "message":      "Free plan active. Save your API key.",
        }

    if plan not in PLAN_DETAILS:
        raise HTTPException(400, f"Invalid plan: {plan}")

    price_id = PRICE_IDS.get(plan, "")
    if not price_id:
        raise HTTPException(500, f"PADDLE_PRICE_{plan.upper()} not configured")

    workspace_id = f"ws_{secrets.token_hex(8)}"

    # Return data for Paddle.js inline checkout (client-side)
    # The frontend will use Paddle.Checkout.open() with these details
    return {
        "price_id":     price_id,
        "email":        body.email,
        "workspace_id": workspace_id,
        "plan":         plan,
        "custom_data": {
            "workspace_id": workspace_id,
            "plan":         plan,
            "email":        body.email,
        },
        "success_url": f"{APP_URL}/success?workspace={workspace_id}&plan={plan}",
    }


@router.post("/webhook")
async def paddle_webhook(
    request: Request,
    paddle_signature: Optional[str] = Header(None, alias="Paddle-Signature"),
):
    body = await request.body()

    # Verify Paddle webhook signature
    if not PADDLE_WEBHOOK_SECRET:
        raise HTTPException(500, "PADDLE_WEBHOOK_SECRET not configured")

    if not paddle_signature:
        raise HTTPException(400, "Missing Paddle-Signature header")

    # Paddle signature format: ts=...;h1=...
    try:
        parts  = dict(p.split("=", 1) for p in paddle_signature.split(";"))
        ts     = parts["ts"]
        sig_h1 = parts["h1"]
    except Exception:
        raise HTTPException(400, "Malformed Paddle-Signature")

    signed  = f"{ts}:{body.decode()}"
    expected = hmac.new(
        PADDLE_WEBHOOK_SECRET.encode(),
        signed.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, sig_h1):
        raise HTTPException(400, "Invalid webhook signature")

    # Replay protection — reject events older than 5 mins
    if abs(int(time.time()) - int(ts)) > 300:
        raise HTTPException(400, "Webhook timestamp too old")

    event = json.loads(body)
    event_type = event.get("event_type", "")
    data       = event.get("data", {})
    custom     = data.get("custom_data", {})

    log.info("Paddle webhook: %s", event_type)

    if event_type == "subscription.activated":
        email        = custom.get("email") or data.get("customer", {}).get("email", "")
        plan         = custom.get("plan", "solo")
        workspace_id = custom.get("workspace_id", f"ws_{secrets.token_hex(8)}")
        await provision_and_email(email, plan, workspace_id)

    elif event_type == "subscription.canceled":
        workspace_id = custom.get("workspace_id", "")
        log.info("Subscription canceled: workspace=%s", workspace_id)
        # TODO: downgrade to free in Redis

    elif event_type == "transaction.payment_failed":
        email = data.get("customer", {}).get("email", "")
        log.warning("Payment failed for %s", email)

    elif event_type == "subscription.updated":
        workspace_id = custom.get("workspace_id", "")
        new_plan     = custom.get("plan", "")
        log.info("Plan updated: workspace=%s plan=%s", workspace_id, new_plan)

    return {"received": True, "event": event_type}


@router.get("/success")
async def checkout_success(workspace: str = ""):
    return {
        "status":  "active",
        "message": "Payment successful. Check your email for your API key.",
        "workspace_id": workspace,
    }
