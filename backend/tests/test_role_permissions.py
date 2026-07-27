"""Unit tests for four-tier feature / action permission catalog."""
from app.utils.permissions import (
    can_access_feature,
    can_perform,
    permissions_for_role,
)


def test_partner_only_lockdowns():
    for feature in (
        "dsc_password_vault",
        "benchmarking",
        "rfp_bids",
        "profitability_audit",
        "peer_review_qc",
    ):
        assert can_access_feature("partner", feature)
        assert not can_access_feature("manager", feature)
        assert not can_access_feature("article", feature)


def test_staff_can_draft_assurance_but_not_sign():
    assert can_access_feature("article", "ca_certificates")
    assert can_access_feature("article", "audit_papers")
    assert can_access_feature("article", "notice_drafter")
    assert not can_perform("article", "certificate:sign")
    assert not can_perform("article", "audit:sign")
    assert not can_perform("article", "notice:approve")
    assert can_perform("manager", "certificate:sign")
    assert can_perform("manager", "audit:sign")


def test_gap_modules_staff_plus():
    for feature in (
        "engagement_kyc",
        "litigation_tracker",
        "tds_tcs_reconciliation",
        "query_observation_ledger",
        "statutory_checklist",
        "roc_xbrl_tracker",
        "einvoice_irn",
        "sop_knowledge_base",
    ):
        assert can_access_feature("article", feature)
        assert can_access_feature("manager", feature)
        assert can_access_feature("partner", feature)


def test_manager_plus_growth_ops():
    assert can_access_feature("manager", "client_risk_scoring")
    assert can_access_feature("manager", "virtual_cfo_mis")
    assert not can_access_feature("article", "client_risk_scoring")
    assert not can_access_feature("article", "billing_collections")


def test_signoff_actions_manager_plus():
    for action in (
        "engagement:approve",
        "litigation:close",
        "observation:close",
        "checklist:signoff",
        "reconciliation:approve",
    ):
        assert can_perform("manager", action)
        assert can_perform("partner", action)
        assert not can_perform("article", action)


def test_permissions_for_role_nonempty():
    assert "vault:manage" in permissions_for_role("partner")
    assert "vault:manage" not in permissions_for_role("manager")
    assert "certificate:sign" in permissions_for_role("manager")
    assert "certificate:sign" not in permissions_for_role("article")
