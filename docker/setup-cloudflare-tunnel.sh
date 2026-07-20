#!/usr/bin/env bash
# Configure Cloudflare Tunnel ingress (catch-all → Caddy :9080) and Access apps.
# Requires: CLOUDFLARE_API_TOKEN with Zone.DNS + Account.Cloudflare Tunnel + Access: Apps and Policies
#
# Usage:
#   export CLOUDFLARE_API_TOKEN=...
#   ./docker/setup-cloudflare-tunnel.sh
#
# Tunnel/account IDs for tetrazero (from cloudflared tunnel list + token payload):
#   ACCOUNT_ID=04b24ad5413da4511d033291ca96d634
#   TUNNEL_ID=aeade0d6-e7af-4a0d-89cf-3c7f9b46d59b

set -euo pipefail

ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-04b24ad5413da4511d033291ca96d634}"
TUNNEL_ID="${CLOUDFLARE_TUNNEL_ID:-aeade0d6-e7af-4a0d-89cf-3c7f9b46d59b}"
API="${CLOUDFLARE_API_BASE:-https://api.cloudflare.com/client/v4}"

if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  echo "Set CLOUDFLARE_API_TOKEN (Account:Cloudflare Tunnel Edit, Access: Apps and Policies Edit, Zone:DNS Edit)." >&2
  exit 1
fi

auth() { curl -fsS -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" -H "Content-Type: application/json" "$@"; }

echo "==> Setting tunnel ingress to Caddy :9080 (all hostnames)"
auth -X PUT "${API}/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
  --data '{
    "config": {
      "ingress": [
        {"service": "http://localhost:9080"},
        {"service": "http_status:404"}
      ]
    }
  }' | python3 -m json.tool

for host in anime.tetrazero.com observability.tetrazero.com; do
  echo "==> Ensuring DNS CNAME for ${host}"
  zone_id=$(auth "${API}/zones?name=tetrazero.com" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result'][0]['id'])")
  auth -X POST "${API}/zones/${zone_id}/dns_records" \
    --data "{\"type\":\"CNAME\",\"name\":\"${host%.tetrazero.com}\",\"content\":\"${TUNNEL_ID}.cfargotunnel.com\",\"proxied\":true}" \
    2>/dev/null || echo "  (DNS record may already exist — update in dashboard if needed)"
done

echo "==> Cloudflare Access applications (create if missing)"
# Access API uses a different base path under Zero Trust
ZT_API="https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/access/apps"

create_access_app() {
  local domain="$1"
  local name="$2"
  auth -X POST "${ZT_API}" --data "{
    \"name\": \"${name}\",
    \"domain\": \"${domain}\",
    \"type\": \"self_hosted\",
    \"session_duration\": \"24h\",
    \"auto_redirect_to_identity\": true
  }" | python3 -m json.tool || true
}

create_access_app "anime.tetrazero.com" "AnimeManager"
create_access_app "observability.tetrazero.com" "AnimeManager Observability"

echo ""
echo "Done. Add Allow policies in Zero Trust → Access → Applications if the API did not attach one."
echo "Verify: curl -I https://anime.tetrazero.com  (expect 302 to Cloudflare Access login)"
