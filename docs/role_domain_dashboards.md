# Four role domains (separate dashboards)

Each firm role and the client portal run as a **separate public domain**.
Logging in with a role’s demo ID lands on that role’s domain only — not a shared sidebar shell.

## Domains

| Desk | Env desk key | Default path | Demo email |
|---|---|---|---|
| Firm Head / Partner | `partner` | `/workspaces/partner` | `partner@cacopilot.example.com` |
| CA (Manager) | `manager` | `/workspaces/ca` | `ca@cacopilot.example.com` |
| Intern / Staff | `article` | `/workspaces/staff` | `staff@cacopilot.example.com` |
| Client | `client` | `/client-portal` | `client@apex.example.com` |

A fifth **hub** host (optional, usually `localhost:3000`) lists the four domains and redirects after login.

## Configuration

```bash
# host → desk
ROLE_DOMAIN_MAP=partner.example.com=partner,ca.example.com=manager,staff.example.com=article,portal.example.com=client
NEXT_PUBLIC_ROLE_DOMAIN_MAP="$ROLE_DOMAIN_MAP"

# absolute URLs used after hub login
NEXT_PUBLIC_ROLE_DOMAIN_URLS=partner=https://partner.example.com,manager=https://ca.example.com,article=https://staff.example.com,client=https://portal.example.com

# backend CORS
FRONTEND_URL=https://hub.example.com
FRONTEND_URLS=https://partner.example.com,https://ca.example.com,https://staff.example.com,https://portal.example.com
```

## Preview helper

```bash
bash scripts/start_role_domain_preview.sh
source /tmp/ca-role-domains/env.sh
# restart Next + uvicorn with those exports
```

## Behaviour

- Middleware stamps `ca_app_desk` from the hostname and blocks cross-desk routes.
- Partner domain cannot open `/workspaces/ca` (or staff/client surfaces).
- Login sends `X-Expected-Role`; API returns 403 on mismatch.
- Domain-bound desks hide “Open full modules” and never mount the shared command-deck sidebar.
