# Deploy ContextMesh — Run these commands in order

## Prerequisites
- flyctl installed: curl -L https://fly.io/install.sh | sh
- Logged in: fly auth login

## Step 1 — Create the app
fly apps create contextmesh-api

## Step 2 — Create persistent volume (embedding cache)
fly volumes create contextmesh_embed_cache \
  --size 1 \
  --region ams \
  --app contextmesh-api

## Step 3 — Set all secrets (fill in Paddle keys first)
bash set_secrets.sh

## Step 4 — Deploy
bash deploy.sh

## Step 5 — Add custom domain
fly certs add contextmesh.dev --app contextmesh-api
fly certs add api.contextmesh.dev --app contextmesh-api

## Step 6 — Get your IP for Cloudflare DNS
fly ips list --app contextmesh-api

## Step 7 — Verify
curl https://api.contextmesh.dev/health
