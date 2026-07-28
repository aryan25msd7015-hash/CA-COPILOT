"""Main audit orchestrator APIs: L1 -> L2 -> L3 -> L4."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.plugins.layer1_audit_engine import default_plugin
from app.plugins.layer2_risk_fusion import plugin_for_org
from app.plugins.layer3_causal_engine import Layer3Engine
from app.plugins.layer4_ai_auditor_agent import Layer4AIAuditorAgent
from app.services.audit_trail import ImmutableAuditTrail
from app.utils.deps import get_current_user, require_feature

router = APIRouter()
_layer1 = default_plugin()
_layer3 = Layer3Engine()
_layer4 = Layer4AIAuditorAgent()
_trail = ImmutableAuditTrail(Path("/tmp/ca_audit_trail/audit_trail.jsonl"))
_investigations: dict[str, dict[str, Any]] = {}


class AuditTxnRequest(BaseModel):
    txn_id: str
    account_id: str
    amount: float = Field(gt=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    pan: str | None = None
    gstin: str | None = None
    device_id: str | None = None
    beneficiary_account: str | None = None
    is_new_beneficiary: bool = False
    days_since_beneficiary_added: int = 9999
    txn_count_24h: int = 1
    total_amount_24h: float = 0.0
    txn_count_1h: int = 1
    total_amount_1h: float = 0.0
    days_since_last_txn: int = 0
    is_round_amount: bool = False
    is_international: bool = False
    pan_gstin_mismatch: bool = False
    device_change_24h: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, float] = Field(default_factory=dict)
    history: list[dict[str, float]] = Field(default_factory=list)
    graph_edges: list[tuple[str, str, float]] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    investigation_id: str
    approved: bool


@router.post("/audit_txn")
def audit_txn(
    payload: AuditTxnRequest,
    request: Request,
    _=Depends(require_feature("ai_audit_orchestrator")),
    __=Depends(get_current_user),
):
    txn = payload.model_dump()
    l1_output = _layer1.audit_txn(txn)
    l2_row = {
        "id": payload.txn_id,
        "org_id": getattr(request.state, "org_id", None),
        "client_id": payload.metadata.get("client_id", "manual"),
        "vendor_gstin": payload.gstin or "27UNKNOWN0000A1Z5",
        "vendor_name": payload.metadata.get("vendor_name", "Unknown Vendor"),
        "invoice_no": payload.metadata.get("invoice_no", payload.txn_id),
        "amount": payload.amount,
        "tax_amount": payload.metadata.get("tax_amount", 0.0),
        "date": payload.timestamp.date(),
        "match_status": payload.metadata.get("match_status", "unmatched"),
        "fraud_flag": payload.metadata.get("fraud_flag"),
    }
    l2_output = plugin_for_org(getattr(request.state, "org_id", None)).analyze_batch([l2_row])
    l2_txn = (l2_output.get("transactions") or [{}])[0]
    l3_output = _layer3.analyze(
        txn={"account_id": payload.account_id, "amount": payload.amount},
        features=payload.features,
        history=payload.history,
        graph_edges=payload.graph_edges,
    )
    l4_output = _layer4.investigate(
        {
            "txn_id": payload.txn_id,
            "account_id": payload.account_id,
            "amount": payload.amount,
            "metadata": {"gstin": payload.gstin, **payload.metadata},
            "l1_output": l1_output,
            "l2_output": l2_txn,
            "l3_output": l3_output,
        }
    )
    investigation_id = str(uuid4())
    response = {
        "investigation_id": investigation_id,
        "final_risk": l4_output["final_risk"],
        "remark": l4_output["remark"],
        "risk_score": l4_output["evidence_pack"].get("composite_score", l2_txn.get("risk_probability", 0.0)),
        "proof": l1_output.get("proof", {}),
        "evidence_pack": l4_output["evidence_pack"],
        "pipeline": {"l1": l1_output, "l2": l2_output, "l3": l3_output, "l4": l4_output},
    }
    _investigations[investigation_id] = response
    _trail.write_event("audit_txn", response)
    return response


@router.post("/audit_txn/feedback")
def submit_feedback(
    payload: FeedbackRequest,
    _=Depends(require_feature("ai_audit_orchestrator")),
    __=Depends(get_current_user),
):
    investigation = _investigations.get(payload.investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="investigation_id not found")
    rl = _layer4.apply_ca_feedback(payload.approved)
    result = {
        "investigation_id": payload.investigation_id,
        "approved": payload.approved,
        "rl_update": rl,
    }
    _trail.write_event("ca_feedback", result)
    return result
