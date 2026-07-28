"""Layer-1 Logic Audit plugin APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.plugins.layer1_audit_engine import default_plugin
from app.utils.deps import require_feature

router = APIRouter()
_plugin = default_plugin()


class AuditTxnRequest(BaseModel):
    txn: dict


@router.get("/status")
def status(_=Depends(require_feature("logic_audit_layer1"))):
    return {
        "plugin": "layer1_logic_audit",
        "status": "active",
        "rules_loaded": len(_plugin.rule_engine.rules),
        "severity_catalog": sorted({rule.severity for rule in _plugin.rule_engine.rules}),
        "graph_nodes": _plugin.graph.graph.number_of_nodes(),
        "graph_edges": _plugin.graph.graph.number_of_edges(),
    }


@router.post("/audit-txn")
def audit_txn(payload: AuditTxnRequest, _=Depends(require_feature("logic_audit_layer1"))):
    return _plugin.audit_txn(payload.txn)
