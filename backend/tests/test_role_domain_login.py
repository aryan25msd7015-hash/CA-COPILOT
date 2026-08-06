"""Role-domain expected-role guard."""

import pytest
from fastapi import HTTPException

from app.routers.auth import enforce_expected_desk_role


def test_enforce_expected_desk_role_allows_match():
    enforce_expected_desk_role("partner", "partner")
    enforce_expected_desk_role("manager", None)
    enforce_expected_desk_role("article", "")


def test_enforce_expected_desk_role_rejects_mismatch():
    with pytest.raises(HTTPException) as exc:
        enforce_expected_desk_role("partner", "manager")
    assert exc.value.status_code == 403
    assert "manager" in str(exc.value.detail).lower()
