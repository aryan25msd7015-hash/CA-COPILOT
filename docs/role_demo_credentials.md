# Four-tier demo credentials

Use these accounts after running:

```bash
cd backend && python scripts/seed_demo_data.py
```

| Role | Email | Password | Landing |
|---|---|---|---|
| Firm Head / Partner | `partner@cacopilot.example.com` | `PartnerDemo123` | `/workspaces/partner` |
| CA (Manager) | `ca@cacopilot.example.com` | `CADemo123` | `/workspaces/ca` |
| Intern / Staff | `staff@cacopilot.example.com` | `StaffDemo123` | `/workspaces/staff` |
| Client | `client@apex.example.com` | `ClientDemo123` | `/client-portal` |

Legacy partner alias still works for existing e2e:

- `demo@cacopilot.example.com` / `DemoPass123`

## Notes

- Firm Head desk includes **Assign clients to CA**.
- CA desk only lists clients assigned to that manager.
- Client uses portal auth (`/client-portal/auth/demo-login` in non-production).
- Full module shell remains available via “Open full modules” inside each role desk.
