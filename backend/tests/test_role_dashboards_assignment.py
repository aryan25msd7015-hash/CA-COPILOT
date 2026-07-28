from app.schemas.client import ClientAssignRequest, ClientCreate, ClientListOut, ClientOut
from app.utils.demo_credentials import DEMO_ACCOUNTS, LEGACY_PARTNER_EMAIL


def test_demo_accounts_cover_four_tiers() -> None:
    tiers = {item["tier"] for item in DEMO_ACCOUNTS}
    assert tiers == {"partner", "manager", "article", "client"}
    assert LEGACY_PARTNER_EMAIL == "demo@cacopilot.example.com"


def test_client_assign_schema_accepts_null() -> None:
    payload = ClientAssignRequest(assigned_ca_user_id=None)
    assert payload.assigned_ca_user_id is None


def test_client_out_includes_assignment_fields() -> None:
    fields = set(ClientOut.model_fields.keys())
    assert "assigned_ca_user_id" in fields
    assert "assigned_ca_email" in fields
    assert "assigned_ca_user_id" in ClientListOut.model_fields
    assert "assigned_ca_user_id" in ClientCreate.model_fields
