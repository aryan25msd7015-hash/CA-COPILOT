import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
from typing import Any, Optional

from app.database import get_db
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.system import OrganizationAgentState
from app.models.system import SystemAuditLog
from app.models.user import User
from app.utils.deps import get_current_user, require_role

router = APIRouter()


def _create_agent_readiness(org_id: UUID) -> OrganizationAgentState:
    return OrganizationAgentState(
        org_id=org_id,
        status="ready",
        vector_namespace=f"org_{org_id}",
        enabled_agents=[
            "autopilot",
            "notice_drafter",
            "nl_query",
            "benchmarking",
            "voice_agent",
        ],
        readiness_checks={
            "tenant_partition": True,
            "default_roles": ["partner", "manager", "article"],
            "vector_namespace": f"org_{org_id}",
            "event": "organization.initialized",
            "provisioned_from": "readiness_backfill",
        },
        last_event="organization.initialized",
    )


class OrgOut(BaseModel):
    id: UUID
    name: str
    plan: str
    gstin: Optional[str] = None
    pan: Optional[str] = None
    frn: Optional[str] = None
    status: str = "active"
    firm_type: str = "ca_firm"
    registered_state: Optional[str] = None
    jurisdictions: list[str] = []
    compliance_profile: dict[str, Any] = {}
    automation_policy: dict[str, Any] = {}
    data_residency_region: str = "IN"
    key_vault_ref: Optional[str] = None
    security_policy: dict[str, Any] = {}
    config_version: int = 1
    model_config = {"from_attributes": True}


class AgentReadinessOut(BaseModel):
    status: str
    vector_namespace: str
    enabled_agents: list[str]
    readiness_checks: dict
    last_event: str
    model_config = {"from_attributes": True}


class OrgReadinessOut(BaseModel):
    organization: OrgOut
    agent_readiness: Optional[AgentReadinessOut] = None


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    frn: Optional[str] = None
    firm_type: Optional[str] = None
    registered_state: Optional[str] = None
    jurisdictions: Optional[list[str]] = None
    compliance_profile: Optional[dict[str, Any]] = None
    automation_policy: Optional[dict[str, Any]] = None
    data_residency_region: Optional[str] = None
    key_vault_ref: Optional[str] = None
    security_policy: Optional[dict[str, Any]] = None
    force_session_reset: bool = False

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("Organization name cannot be blank")
        return value.strip() if value is not None else value

    @field_validator("gstin")
    @classmethod
    def valid_gstin(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = value.strip().upper()
        if len(normalized) != 15 or not normalized.isalnum():
            raise ValueError("GSTIN must be 15 alphanumeric characters")
        return normalized

    @field_validator("pan")
    @classmethod
    def valid_pan(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", normalized):
            raise ValueError("PAN must use the standard 10-character format")
        return normalized

    @field_validator("frn")
    @classmethod
    def valid_frn(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = value.strip().upper()
        if len(normalized) > 20 or not re.fullmatch(r"[A-Z0-9/-]+", normalized):
            raise ValueError("FRN must be 20 characters or fewer using letters, digits, slash, or hyphen")
        return normalized

    @field_validator("firm_type")
    @classmethod
    def valid_firm_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        allowed = {"ca_firm", "solo_ca", "multi_partner_firm", "enterprise_practice"}
        if normalized not in allowed:
            raise ValueError("Invalid firm_type")
        return normalized

    @field_validator("registered_state")
    @classmethod
    def valid_state(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = value.strip().upper()
        if len(normalized) > 40:
            raise ValueError("Registered state is too long")
        return normalized

    @field_validator("jurisdictions")
    @classmethod
    def valid_jurisdictions(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        normalized = sorted({item.strip().upper() for item in value if item and item.strip()})
        if len(normalized) > 36:
            raise ValueError("Too many jurisdictions configured")
        return normalized

    @field_validator("automation_policy")
    @classmethod
    def valid_automation_policy(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        mode = value.get("mode", "draft_only")
        if mode not in {"draft_only", "hybrid_autopilot", "full_autopilot"}:
            raise ValueError("Invalid automation policy mode")
        confidence = float(value.get("min_confidence_score", 0.95))
        if confidence < 0 or confidence > 1:
            raise ValueError("min_confidence_score must be between 0 and 1")
        return {**value, "mode": mode, "min_confidence_score": confidence}

    @field_validator("data_residency_region")
    @classmethod
    def valid_residency(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized not in {"IN", "AP_SOUTH_1"}:
            raise ValueError("Only Indian data residency is currently supported")
        return normalized


def _critical_profile_change(req: OrgUpdate) -> bool:
    changed = req.model_dump(exclude_none=True)
    return req.force_session_reset or any(key in changed for key in {"security_policy", "data_residency_region", "key_vault_ref"})


def _invalidate_org_sessions(db: Session, org_id: UUID) -> int:
    revoked_at = datetime.now(timezone.utc)
    user_ids = [row[0] for row in db.query(User.id).filter(User.org_id == org_id).all()]
    db.query(User).filter(User.org_id == org_id).update({"tokens_revoked_at": revoked_at}, synchronize_session=False)
    if not user_ids:
        return 0
    return db.query(RefreshToken).filter(
        RefreshToken.org_id == org_id,
        RefreshToken.revoked.is_(False),
    ).update({"revoked": True, "revoked_at": revoked_at}, synchronize_session=False)


@router.get("/me", response_model=OrgOut)
def get_my_org(request: Request, db: Session = Depends(get_db),
               _=Depends(get_current_user)):
    org = db.query(Organization).filter(
        Organization.id == request.state.org_id).first()
    if not org:
        raise HTTPException(404, "Organization not found")
    return org


@router.get("/me/readiness", response_model=OrgReadinessOut)
def get_org_readiness(request: Request, db: Session = Depends(get_db),
                      _=Depends(get_current_user)):
    org = db.query(Organization).filter(Organization.id == request.state.org_id).first()
    if not org:
        raise HTTPException(404, "Organization not found")
    readiness = db.query(OrganizationAgentState).filter(
        OrganizationAgentState.org_id == request.state.org_id
    ).first()
    if not readiness:
        readiness = _create_agent_readiness(org.id)
        db.add(readiness)
        db.commit()
        db.refresh(readiness)
    return {"organization": org, "agent_readiness": readiness}


@router.patch("/me", response_model=OrgOut)
def update_my_org(req: OrgUpdate, request: Request,
                  db: Session = Depends(get_db),
                  _=Depends(require_role(["partner"]))):
    org = db.query(Organization).filter(
        Organization.id == request.state.org_id).first()
    if not org:
        raise HTTPException(404, "Organization not found")
    updates = req.model_dump(exclude_none=True, exclude={"force_session_reset"})
    if "pan" in updates:
        existing = db.query(Organization).filter(
            Organization.pan == updates["pan"],
            Organization.id != org.id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Organization PAN already registered")
    for key, val in updates.items():
        setattr(org, key, val)
    org.config_version = (org.config_version or 1) + 1
    sessions_invalidated = _invalidate_org_sessions(db, org.id) if _critical_profile_change(req) else 0
    db.add(SystemAuditLog(
        org_id=org.id,
        actor_id=request.state.user_id,
        action="ORG_PROFILE_UPDATED",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        payload={
            "changed_fields": sorted(updates.keys()),
            "sessions_invalidated": sessions_invalidated,
            "config_version": org.config_version,
        },
    ))
    db.commit()
    db.refresh(org)
    return org
