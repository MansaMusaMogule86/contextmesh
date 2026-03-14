#!/usr/bin/env bash
# ContextMesh — Set all Fly.io secrets
# Usage: edit the values below then run: bash set_secrets.sh
set -euo pipefail

APP="contextmesh-api"

echo "Setting Fly.io secrets for app: $APP"
echo ""

fly secrets set \
  QDRANT_URL="https://7314087f-d084-4b18-a243-8a44b2c0ee48.europe-west3-0.gcp.cloud.qdrant.io" \
  QDRANT_API_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.Vb0WK36LgUQePeVekxtcXlnZwVrv9ql3OiE_Uwehwjo" \
  OPENAI_API_KEY="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" \
  REDIS_URL="rediss://default:gQAAAAAAARUlAAIncDI2ODExY2ZlYTM3YjE0MjdlODNlOTJhYTY5NjM4OTBlMHAyNzA5NDk@musical-monkey-70949.upstash.io:6379" \
  RESEND_API_KEY="re_54Cn54iS_3AjAZQpg4aTnNzCeneaLa3Mv" \
  PADDLE_API_KEY="pdl_live_apikey_01kkmv6zbrg3v762mbfben7gqp_EHJx7jtV3cdbMpVsCKrtze_Aaj" \
  PADDLE_WEBHOOK_SECRET="pdl_ntfset_01kkmvbt9capfgzzfjd8hq3fxd_1kfYxKCi+vESfERVxWmH6wxkmnAQuD84" \
  PADDLE_PRICE_SOLO="pri_01kkmrmchq5ntj3s86gnn75gst" \
  PADDLE_PRICE_TEAM="pri_01kkmrkz4v6d3cjcz46dxdq6dk" \
  PADDLE_PRICE_ENTERPRISE="pri_01kkmrjz6mzqmyw894t17njt7x" \
  CONTEXTMESH_SECRET="$(openssl rand -hex 32)" \
  APP_URL="https://contextmesh.dev" \
  API_URL="https://api.contextmesh.dev" \
  CONTEXTMESH_ENV="production" \
  FROM_EMAIL="keys@contextmesh.dev" \
  PORT="8080" \
  WORKERS="2" \
  --app "$APP"

echo ""
echo "✓ All secrets set. Run ./deploy.sh to deploy."
