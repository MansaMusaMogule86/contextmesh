#!/usr/bin/env bash
# ContextMesh — Deploy to Fly.io
# Usage: ./deploy.sh [--prod|--staging]
set -euo pipefail

ENV="${1:-}"
APP="contextmesh-api"
[[ "$ENV" == "--staging" ]] && APP="contextmesh-api-staging"

echo "╔══════════════════════════════════════╗"
echo "║   ContextMesh Deploy → Fly.io        ║"
echo "║   App: $APP"
echo "╚══════════════════════════════════════╝"

# ── Pre-flight checks ─────────────────────────────────────────────────────────
echo ""
echo "▶ Checking dependencies..."

command -v fly  &>/dev/null || { echo "✗ flyctl not found. Install: curl -L https://fly.io/install.sh | sh"; exit 1; }
command -v docker &>/dev/null || { echo "✗ Docker not found. Install from docker.com"; exit 1; }

echo "  ✓ flyctl $(fly version | head -1)"
echo "  ✓ docker $(docker --version | cut -d' ' -f3 | tr -d ',')"

# ── Check secrets ─────────────────────────────────────────────────────────────
echo ""
echo "▶ Checking required secrets..."

SECRETS=$(fly secrets list --app "$APP" 2>/dev/null || echo "")

check_secret() {
  local name="$1" required="$2"
  if echo "$SECRETS" | grep -q "^$name"; then
    echo "  ✓ $name"
  elif [[ "$required" == "required" ]]; then
    echo "  ✗ $name (MISSING — required)"
    MISSING_SECRETS=1
  else
    echo "  △ $name (optional)"
  fi
}

MISSING_SECRETS=0
check_secret "OPENAI_API_KEY"         required
check_secret "CONTEXTMESH_SECRET"     required
check_secret "PADDLE_API_KEY"         required
check_secret "PADDLE_WEBHOOK_SECRET"  required
check_secret "PADDLE_PRICE_SOLO"      required
check_secret "PADDLE_PRICE_TEAM"      required
check_secret "PADDLE_PRICE_ENTERPRISE" required
check_secret "QDRANT_URL"             required
check_secret "REDIS_URL"              required
check_secret "RESEND_API_KEY"         optional

if [[ "$MISSING_SECRETS" -eq 1 ]]; then
  echo ""
  echo "Set missing secrets with:"
  echo "  bash set_secrets.sh"
  exit 1
fi

# ── Run tests ─────────────────────────────────────────────────────────────────
echo ""
echo "▶ Running test suite..."
if command -v pytest &>/dev/null; then
  pytest tests/ -q --tb=short 2>&1 | tail -5
  echo "  ✓ Tests passed"
else
  echo "  △ pytest not found — skipping tests"
fi

# ── Deploy ────────────────────────────────────────────────────────────────────
echo ""
echo "▶ Deploying to Fly.io..."
fly deploy --app "$APP" --strategy rolling --wait-timeout 120

echo ""
echo "▶ Post-deploy health check..."
sleep 5
STATUS=$(fly status --app "$APP" | grep -c "running" || true)
if [[ "$STATUS" -gt 0 ]]; then
  echo "  ✓ $STATUS machine(s) running"
else
  echo "  △ Status unclear — check: fly status --app $APP"
fi

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  ✓ Deploy complete!                  ║"
echo "║  URL: https://api.contextmesh.dev    ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Monitor:"
echo "  fly logs --app $APP"
echo "  fly status --app $APP"
