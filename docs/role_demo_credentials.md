# Four-tier demo credentials

Use these accounts after running:

```bash
cd backend && python scripts/seed_demo_data.py
```

| Role | Email | Password | Domain desk | Landing |
|---|---|---|---|---|
| Firm Head / Partner | `partner@cacopilot.example.com` | `PartnerDemo123` | `partner` | `/workspaces/partner` |
| CA (Manager) | `ca@cacopilot.example.com` | `CADemo123` | `manager` | `/workspaces/ca` |
| Intern / Staff | `staff@cacopilot.example.com` | `StaffDemo123` | `article` | `/workspaces/staff` |
| Client | `client@apex.example.com` | `ClientDemo123` | `client` | `/client-portal` |

Legacy partner alias still works for existing e2e:

- `demo@cacopilot.example.com` / `DemoPass123`

## Notes

- Firm Head desk includes **Assign clients to CA**.
- CA desk only lists clients assigned to that manager.
- Client uses portal auth (`/client-portal/auth/demo-login` in non-production).
- When `ROLE_DOMAIN_MAP` is set, each role opens on its **own domain**. See `docs/role_domain_dashboards.md`.
- On a role domain, “Open full modules” is disabled — that desk stays isolated.
