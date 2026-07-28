"""Shared demo login catalog for four-tier role testing."""

DEMO_ACCOUNTS = [
    {
        "tier": "partner",
        "label": "Firm Head / Partner",
        "email": "partner@cacopilot.example.com",
        "password": "PartnerDemo123",
        "workspace": "/workspaces/partner",
        "auth": "firm",
    },
    {
        "tier": "manager",
        "label": "CA (Manager)",
        "email": "ca@cacopilot.example.com",
        "password": "CADemo123",
        "workspace": "/workspaces/ca",
        "auth": "firm",
    },
    {
        "tier": "article",
        "label": "Intern / Staff",
        "email": "staff@cacopilot.example.com",
        "password": "StaffDemo123",
        "workspace": "/workspaces/staff",
        "auth": "firm",
    },
    {
        "tier": "client",
        "label": "Client",
        "email": "client@apex.example.com",
        "password": "ClientDemo123",
        "workspace": "/client-portal",
        "auth": "portal",
    },
]

# Keep legacy partner demo as alias for existing e2e scripts.
LEGACY_PARTNER_EMAIL = "demo@cacopilot.example.com"
LEGACY_PARTNER_PASSWORD = "DemoPass123"
