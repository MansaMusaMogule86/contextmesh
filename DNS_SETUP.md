## Cloudflare DNS Setup for contextmesh.dev
## Do this AFTER fly deploy gives you an IP/hostname

# ── Step 1: Add these DNS records in Cloudflare ───────────────────────────────
# dash.cloudflare.com → contextmesh.dev → DNS → Add record

# Root domain → landing page
Type: CNAME
Name: @  (or contextmesh.dev)
Target: contextmesh-api.fly.dev
Proxy: ON (orange cloud)

# API subdomain → your API
Type: CNAME
Name: api
Target: contextmesh-api.fly.dev
Proxy: ON (orange cloud)

# ── Step 2: SSL ───────────────────────────────────────────────────────────────
# Cloudflare → SSL/TLS → set to "Full (strict)"
# Fly.io handles the cert automatically

# ── Step 3: Verify ───────────────────────────────────────────────────────────
# curl https://api.contextmesh.dev/health
# Should return: {"status":"ok","service":"contextmesh"}
