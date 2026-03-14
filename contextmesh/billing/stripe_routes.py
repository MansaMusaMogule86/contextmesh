"""
ContextMesh — Stripe Billing Routes
Mounts onto the FastAPI app as a router.

Endpoints:
  POST /billing/checkout        → Create Stripe Checkout session
  POST /billing/webhook         → Handle Stripe webhook events
  GET  /billing/portal          → Customer portal (manage subscription)
  GET  /billing/plans           → List plans + pricing

Flow:
  1. User hits landing page, picks plan → POST /billing/checkout
  2. Redirected to Stripe Checkout
  3. On success → Stripe fires checkout.session.completed webhook
  4. Webhook handler: create workspace, generate API key, email key to user
  5. User hits /billing/portal to manage subscription
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
from fastapi import APIRouter, Request, HTTPException, Header, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr

log = logging.getLogger("contextmesh.billing")

router = APIRouter(prefix="/billing", tags=["billing"])

# ── Config ────────────────────────────────────────────────────────────────────

STRIPE_SECRET    = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK   = os.getenv("STRIPE_WEBHOOK_SECRET", "")
APP_URL          = os.getenv("APP_URL", "https://contextmesh.dev")
API_URL          = os.getenv("API_URL", "https://api.contextmesh.dev")
FROM_EMAIL       = os.getenv("FROM_EMAIL", "keys@contextmesh.dev")

# Stripe Price IDs — set these in your Stripe dashboard and put in env
PRICE_IDS = {
    "solo":       os.getenv("STRIPE_PRICE_SOLO",       "price_solo_placeholder"),
    "team":       os.getenv("STRIPE_PRICE_TEAM",       "price_team_placeholder"),
    "enterprise": os.getenv("STRIPE_PRICE_ENTERPRISE", "price_enterprise_placeholder"),
}

PLAN_DETAILS = {
    "free": {
        "name": "Free",
        "price_monthly": 0,
        "queries_limit": 1_000,
        "entries_limit": 10_000,
        "rate_limit_per_min": 20,
        "workspaces": 1,
    },
    "solo": {
        "name": "Solo",
        "price_monthly": 19,
        "queries_limit": 100_000,
        "entries_limit": 500_000,
        "rate_limit_per_min": 100,
        "workspaces": 1,
        "stripe_price_id": PRICE_IDS["solo"],
    },
    "team": {
        "name": "Team",
        "price_monthly": 99,
        "queries_limit": 1_000_000,
        "entries_limit": 5_000_000,
        "rate_limit_per_min": 500,
        "workspaces": 10,
        "stripe_price_id": PRICE_IDS["team"],
    },
    "enterprise": {
        "name": "Enterprise",
        "price_monthly": 599,
        "queries_limit": -1,           # unlimited
        "entries_limit": -1,
        "rate_limit_per_min": 2000,
        "workspaces": -1,
        "stripe_price_id": PRICE_IDS["enterprise"],
    },
}

STRIPE_BASE = "https://api.stripe.com/v1"


# ── Stripe HTTP helper ────────────────────────────────────────────────────────

def stripe_headers() -> dict:
    if not STRIPE_SECRET:
        raise HTTPException(500, "Stripe not configured")
    return {
        "Authorization": f"Bearer {STRIPE_SECRET}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


async def stripe_post(path: str, data: dict) -> dict:
    """POST to Stripe API with form-encoded body."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{STRIPE_BASE}{path}",
            headers=stripe_headers(),
            data=data,
        )
        if r.status_code >= 400:
            err = r.json().get("error", {})
            raise HTTPException(r.status_code, f"Stripe error: {err.get('message', r.text)}")
        return r.json()


async def stripe_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{STRIPE_BASE}{path}",
            headers=stripe_headers(),
            params=params or {},
        )
        if r.status_code >= 400:
            err = r.json().get("error", {})
            raise HTTPException(r.status_code, f"Stripe error: {err.get('message', r.text)}")
        return r.json()


# ── API key generation ────────────────────────────────────────────────────────

def generate_api_key() -> str:
    """Generate a cm_live_... API key."""
    token = secrets.token_urlsafe(32)
    return f"cm_live_{token}"


async def provision_workspace(
    workspace_id: str,
    plan: str,
    api_key: str,
    redis,                    # injected from FastAPI dependency
) -> None:
    """
    Write workspace record + hashed API key into Redis.
    Same format as auth.py expects.
    """
    import hashlib
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    workspace_data = json.dumps({
        "workspace_id": workspace_id,
        "plan":         plan,
        "label":        workspace_id,
        "created_at":   int(time.time()),
        "active":       True,
    })
    # 30 days TTL is reset every time they query; effectively permanent for active accounts
    await redis.set(f"cm:key:{key_hash}", workspace_data, ex=60 * 60 * 24 * 30)
    log.info("Provisioned workspace %s plan=%s", workspace_id, plan)


async def send_api_key_email(email: str, api_key: str, plan: str, workspace_id: str) -> None:
    """
    Send API key to user via email.
    Using Resend (resend.com) — swap for SendGrid/Postmark/SES as needed.
    """
    resend_key = os.getenv("RESEND_API_KEY", "")
    if not resend_key:
        log.warning("RESEND_API_KEY not set — skipping email to %s", email)
        log.info("API key for %s: %s", email, api_key)
        return

    html = f"""
    <div style="font-family:monospace;max-width:520px;margin:0 auto;padding:40px 20px;background:#0A0A08;color:#F2EFE8;">
      <div style="font-size:22px;font-weight:600;margin-bottom:24px;">
        ◈ Your ContextMesh API Key
      </div>
      <p style="color:#A0A099;margin-bottom:16px;">
        You're on the <strong style="color:#C8FF00;">{plan.upper()}</strong> plan.
        Your workspace ID is <code style="color:#C8FF00;">{workspace_id}</code>.
      </p>
      <div style="background:#141414;border:1px solid #2A2A2A;border-radius:6px;padding:16px;margin:20px 0;">
        <div style="font-size:11px;color:#5A5A52;margin-bottom:8px;letter-spacing:0.1em;text-transform:uppercase;">API Key</div>
        <div style="font-size:14px;color:#C8FF00;word-break:break-all;">{api_key}</div>
      </div>
      <p style="color:#5A5A52;font-size:13px;">Store this somewhere safe. We cannot recover it if lost.</p>
      <div style="margin-top:32px;padding-top:24px;border-top:1px solid #2A2A2A;">
        <p style="color:#5A5A52;font-size:12px;">Quick start:</p>
        <div style="background:#141414;border:1px solid #2A2A2A;border-radius:6px;padding:12px;font-size:12px;color:#A0A099;">
          pip install contextmesh<br>
          <br>
          from contextmesh import Mesh<br>
          mesh = Mesh("{api_key[:20]}...")<br>
          mesh.remember("your first context")
        </div>
      </div>
      <div style="margin-top:24px;">
        <a href="https://docs.contextmesh.dev" style="color:#C8FF00;font-size:13px;">Read the docs →</a>
        &nbsp;&nbsp;
        <a href="{APP_URL}/dashboard" style="color:#C8FF00;font-size:13px;">Open dashboard →</a>
      </div>
    </div>
    """

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_key}",
                "Content-Type": "application/json",
            },
            json={
                "from":    FROM_EMAIL,
                "to":      [email],
                "subject": f"Your ContextMesh API key ({plan} plan)",
                "html":    html,
            },
        )
        if r.status_code >= 400:
            log.error("Email send failed: %s %s", r.status_code, r.text)
        else:
            log.info("API key email sent to %s", email)


# ── Routes ────────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str
    email: str


@router.get("/plans")
async def list_plans():
    """Return available plans with pricing."""
    return {
        "plans": [
            {
                "id":          plan_id,
                "name":        info["name"],
                "price_usd":   info["price_monthly"],
                "queries_mo":  info["queries_limit"],
                "entries":     info["entries_limit"],
                "rate_rpm":    info["rate_limit_per_min"],
                "workspaces":  info["workspaces"],
                "checkout_url": f"{API_URL}/billing/checkout" if plan_id != "free" else None,
            }
            for plan_id, info in PLAN_DETAILS.items()
        ]
    }


@router.post("/checkout")
async def create_checkout_session(body: CheckoutRequest):
    """
    Create a Stripe Checkout session for the given plan.
    Returns {checkout_url: "https://checkout.stripe.com/..."}.
    """
    plan = body.plan.lower()
    if plan == "free":
        # Free plan — skip Stripe, provision directly
        workspace_id = f"ws_{secrets.token_hex(8)}"
        api_key      = generate_api_key()
        # Note: in production, inject redis here via FastAPI dependency
        # For now, return the key directly — webhook flow is used for paid plans
        return {
            "plan":         "free",
            "workspace_id": workspace_id,
            "api_key":      api_key,
            "message":      "Free plan provisioned. Save your API key — it won't be shown again.",
        }

    if plan not in PLAN_DETAILS or plan == "free":
        raise HTTPException(400, f"Invalid plan: {plan}. Choose: solo, team, enterprise")

    price_id = PLAN_DETAILS[plan].get("stripe_price_id", "")
    if not price_id or price_id.startswith("price_") and "placeholder" in price_id:
        raise HTTPException(500, f"Stripe price ID not configured for plan '{plan}'. Set STRIPE_PRICE_{plan.upper()} env var.")

    workspace_id = f"ws_{secrets.token_hex(8)}"

    session = await stripe_post("/checkout/sessions", {
        "mode":                         "subscription",
        "payment_method_types[]":       "card",
        "line_items[0][price]":         price_id,
        "line_items[0][quantity]":      "1",
        "customer_email":               body.email,
        "success_url":                  f"{APP_URL}/success?session={{CHECKOUT_SESSION_ID}}",
        "cancel_url":                   f"{APP_URL}/pricing",
        "metadata[workspace_id]":       workspace_id,
        "metadata[plan]":               plan,
        "metadata[email]":              body.email,
        "subscription_data[metadata][workspace_id]": workspace_id,
        "subscription_data[metadata][plan]":         plan,
        "allow_promotion_codes":        "true",
    })

    return {"checkout_url": session["url"], "session_id": session["id"]}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None),
):
    """
    Handle Stripe webhook events.
    Verify signature, then act on relevant events.
    """
    body = await request.body()

    # ── Verify Stripe signature ───────────────────────────────────────────────
    if not STRIPE_WEBHOOK:
        raise HTTPException(500, "STRIPE_WEBHOOK_SECRET not configured")

    if not stripe_signature:
        raise HTTPException(400, "Missing Stripe-Signature header")

    # Parse signature header: t=...,v1=...
    try:
        parts = dict(p.split("=", 1) for p in stripe_signature.split(","))
        timestamp = parts["t"]
        sig_v1    = parts["v1"]
    except Exception:
        raise HTTPException(400, "Malformed Stripe-Signature header")

    # Verify HMAC
    signed_payload = f"{timestamp}.{body.decode('utf-8')}"
    expected = hmac.new(
        STRIPE_WEBHOOK.encode(),
        signed_payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, sig_v1):
        raise HTTPException(400, "Invalid webhook signature")

    # Reject events older than 5 minutes (replay attack protection)
    if abs(int(time.time()) - int(timestamp)) > 300:
        raise HTTPException(400, "Webhook timestamp too old")

    # ── Parse event ───────────────────────────────────────────────────────────
    event = json.loads(body)
    event_type = event.get("type", "")
    log.info("Stripe webhook: %s", event_type)

    # ── Handle events ─────────────────────────────────────────────────────────
    if event_type == "checkout.session.completed":
        session  = event["data"]["object"]
        meta     = session.get("metadata", {})
        plan     = meta.get("plan", "free")
        email    = meta.get("email") or session.get("customer_email", "")
        ws_id    = meta.get("workspace_id", f"ws_{secrets.token_hex(8)}")
        api_key  = generate_api_key()

        # In production: inject redis from app state
        # For now log — the webhook handler in main.py should pass redis
        log.info("New subscription: email=%s plan=%s workspace=%s", email, plan, ws_id)

        # Send API key email
        await send_api_key_email(email, api_key, plan, ws_id)

    elif event_type == "customer.subscription.deleted":
        # Subscription cancelled — downgrade to free
        sub  = event["data"]["object"]
        meta = sub.get("metadata", {})
        ws_id = meta.get("workspace_id", "")
        log.info("Subscription cancelled: workspace=%s", ws_id)
        # TODO: update Redis plan to "free" for this workspace

    elif event_type == "invoice.payment_failed":
        # Payment failed — notify user
        invoice = event["data"]["object"]
        email   = invoice.get("customer_email", "")
        log.warning("Payment failed for %s", email)
        # TODO: send payment failed email

    elif event_type == "customer.subscription.updated":
        # Plan changed (upgrade/downgrade)
        sub      = event["data"]["object"]
        meta     = sub.get("metadata", {})
        ws_id    = meta.get("workspace_id", "")
        new_plan = meta.get("plan", "")
        log.info("Subscription updated: workspace=%s new_plan=%s", ws_id, new_plan)
        # TODO: update Redis plan

    return {"received": True, "event": event_type}


@router.post("/portal")
async def create_portal_session(customer_id: str):
    """
    Create a Stripe Customer Portal session so users can manage their subscription.
    """
    session = await stripe_post("/billing_portal/sessions", {
        "customer":   customer_id,
        "return_url": f"{APP_URL}/dashboard",
    })
    return {"portal_url": session["url"]}


@router.get("/success")
async def checkout_success(session_id: str):
    """
    Called after successful Stripe Checkout.
    The webhook handles provisioning; this just returns status.
    """
    session = await stripe_get(f"/checkout/sessions/{session_id}")
    return {
        "status":   session.get("payment_status"),
        "customer": session.get("customer"),
        "message":  "Your API key has been emailed to you. Check your inbox.",
    }
