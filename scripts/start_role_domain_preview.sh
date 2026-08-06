#!/usr/bin/env bash
# Spin four Cloudflare quick tunnels against the same Next.js app and wire
# ROLE_DOMAIN_MAP so each hostname is a dedicated role desk.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLOUDFLARED="${CLOUDFLARED_BIN:-/tmp/cloudflared}"
FE_PORT="${FE_PORT:-3000}"
BE_PORT="${BE_PORT:-8000}"
STATE_DIR="${STATE_DIR:-/tmp/ca-role-domains}"
mkdir -p "$STATE_DIR"

if [[ ! -x "$CLOUDFLARED" ]]; then
  echo "cloudflared not found at $CLOUDFLARED" >&2
  exit 1
fi

tmux_bin() {
  tmux -f /exec-daemon/tmux.portal.conf "$@" 2>/dev/null || tmux "$@"
}

start_tunnel() {
  local name="$1"
  local target="$2"
  tmux_bin has-session -t "=$name" 2>/dev/null && tmux_bin kill-session -t "$name" || true
  tmux_bin new-session -d -s "$name" -c "$ROOT" -- "$CLOUDFLARED" tunnel --url "$target"
}

extract_url() {
  local name="$1"
  local url=""
  for _ in $(seq 1 40); do
    url="$(tmux_bin capture-pane -t "$name:0.0" -p -S -120 | tr -d '\n' | grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1 || true)"
    if [[ -n "$url" ]]; then
      echo "$url"
      return 0
    fi
    sleep 1
  done
  return 1
}

echo "Starting API tunnel..."
start_tunnel tunnel-api "http://127.0.0.1:${BE_PORT}"
API_URL="$(extract_url tunnel-api)"
echo "API: $API_URL"

echo "Starting four role desk tunnels..."
start_tunnel tunnel-partner "http://127.0.0.1:${FE_PORT}"
start_tunnel tunnel-ca "http://127.0.0.1:${FE_PORT}"
start_tunnel tunnel-staff "http://127.0.0.1:${FE_PORT}"
start_tunnel tunnel-client "http://127.0.0.1:${FE_PORT}"
# Optional hub directory on a fifth tunnel
start_tunnel tunnel-hub "http://127.0.0.1:${FE_PORT}"

PARTNER_URL="$(extract_url tunnel-partner)"
CA_URL="$(extract_url tunnel-ca)"
STAFF_URL="$(extract_url tunnel-staff)"
CLIENT_URL="$(extract_url tunnel-client)"
HUB_URL="$(extract_url tunnel-hub)"

partner_host="${PARTNER_URL#https://}"
ca_host="${CA_URL#https://}"
staff_host="${STAFF_URL#https://}"
client_host="${CLIENT_URL#https://}"

ROLE_DOMAIN_MAP="${partner_host}=partner,${ca_host}=manager,${staff_host}=article,${client_host}=client"
ROLE_DOMAIN_URLS="partner=${PARTNER_URL},manager=${CA_URL},article=${STAFF_URL},client=${CLIENT_URL}"
FRONTEND_URLS="${HUB_URL},${PARTNER_URL},${CA_URL},${STAFF_URL},${CLIENT_URL}"
ALLOWED_DEV_ORIGINS="${partner_host},${ca_host},${staff_host},${client_host},${HUB_URL#https://}"

cat > "$STATE_DIR/env.sh" <<EOF
export NEXT_PUBLIC_API_URL="$API_URL"
export PUBLIC_API_URL="$API_URL"
export FRONTEND_URL="$HUB_URL"
export FRONTEND_URLS="$FRONTEND_URLS"
export ROLE_DOMAIN_MAP="$ROLE_DOMAIN_MAP"
export NEXT_PUBLIC_ROLE_DOMAIN_MAP="$ROLE_DOMAIN_MAP"
export ROLE_DOMAIN_URLS="$ROLE_DOMAIN_URLS"
export NEXT_PUBLIC_ROLE_DOMAIN_URLS="$ROLE_DOMAIN_URLS"
export ALLOWED_DEV_ORIGINS="$ALLOWED_DEV_ORIGINS"
EOF

cat > "$STATE_DIR/links.md" <<EOF
# Role domain preview links

| Desk | Domain | Demo login |
|---|---|---|
| Directory / hub | ${HUB_URL}/login | picks a desk domain |
| Firm Head / Partner | ${PARTNER_URL}/login | partner@cacopilot.example.com / PartnerDemo123 |
| CA (Manager) | ${CA_URL}/login | ca@cacopilot.example.com / CADemo123 |
| Intern / Staff | ${STAFF_URL}/login | staff@cacopilot.example.com / StaffDemo123 |
| Client | ${CLIENT_URL}/client-portal/login | client@apex.example.com / ClientDemo123 |

Restart frontend/backend after sourcing:
\`source $STATE_DIR/env.sh\`
EOF

echo
echo "Wrote $STATE_DIR/env.sh and $STATE_DIR/links.md"
cat "$STATE_DIR/links.md"
