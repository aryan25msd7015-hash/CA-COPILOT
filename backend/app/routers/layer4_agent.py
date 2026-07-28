"""Layer-4 AI auditor agent APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.plugins.layer4_ai_auditor_agent import Layer4AIAuditorAgent
from app.utils.deps import require_feature

router = APIRouter()
_agent = Layer4AIAuditorAgent()


class InvestigateRequest(BaseModel):
    txn: dict


class FeedbackRequest(BaseModel):
    approved: bool


class SimulationRequest(BaseModel):
    batch_size: int = Field(default=32, ge=1, le=500)


@router.get("/status")
def status(_=Depends(require_feature("ai_auditor_layer4"))):
    return {
        "plugin": "layer4_ai_auditor_agent",
        "status": "active",
        "audit_trail_size": len(_agent.audit_trail),
    }


@router.post("/investigate")
def investigate(payload: InvestigateRequest, _=Depends(require_feature("ai_auditor_layer4"))):
    return _agent.investigate(payload.txn)


@router.post("/feedback")
def feedback(payload: FeedbackRequest, _=Depends(require_feature("ai_auditor_layer4"))):
    return _agent.apply_ca_feedback(payload.approved)


@router.post("/simulate-nightly")
def simulate_nightly(payload: SimulationRequest, _=Depends(require_feature("ai_auditor_layer4"))):
    return _agent.run_nightly_fraud_simulation(payload.batch_size)
