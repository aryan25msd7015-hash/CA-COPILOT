"""Layer-1 banking compliance plugin: rules + proofs + graph links."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import networkx as nx
from pydantic import BaseModel, Field, field_validator
from z3 import And, BoolVal, RealVal, Solver

logger = logging.getLogger("banking_compliance.layer1")


class RuleCondition(BaseModel):
    field: str | None = None
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains"] | None = None
    value: Any | None = None
    predicate: Literal["is_weekend"] | None = None

    @field_validator("field")
    @classmethod
    def ensure_field_for_op(cls, value: str | None, info: Any) -> str | None:
        op = info.data.get("op")
        if op and not value:
            raise ValueError("field is required when op is set")
        return value


class RuleDefinition(BaseModel):
    rule_id: str
    name: str
    category: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    all_of: list[RuleCondition] = Field(default_factory=list)
    any_of: list[RuleCondition] = Field(default_factory=list)

    @field_validator("rule_id")
    @classmethod
    def validate_rule_id(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("rule_id cannot be empty")
        return cleaned


class TransactionModel(BaseModel):
    txn_id: str
    account_id: str
    amount: float = Field(gt=0)
    timestamp: datetime
    pan: str | None = None
    gstin: str | None = None
    device_id: str | None = None
    beneficiary_account: str | None = None
    is_new_beneficiary: bool = False
    days_since_beneficiary_added: int = 9999
    txn_count_24h: int = 0
    total_amount_24h: float = 0.0
    txn_count_1h: int = 0
    total_amount_1h: float = 0.0
    days_since_last_txn: int = 0
    is_round_amount: bool = False
    is_international: bool = False
    pan_gstin_mismatch: bool = False
    device_change_24h: int = 0

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


@dataclass
class RuleEvaluation:
    hit: bool
    formal_proof: str


class RuleEngine:
    """JSON-configurable rule executor with formal Z3 proof text."""

    def __init__(self, rules: list[RuleDefinition]):
        self.rules = rules

    @classmethod
    def from_json_file(cls, file_path: str | Path) -> "RuleEngine":
        payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
        rules = [RuleDefinition.model_validate(item) for item in payload]
        return cls(rules=rules)

    def evaluate(self, txn: TransactionModel) -> dict[str, RuleEvaluation]:
        results: dict[str, RuleEvaluation] = {}
        for rule in self.rules:
            hit = self._evaluate_rule(rule, txn)
            formal_proof = self._build_formal_proof(rule, txn, hit=hit)
            self._audit_log(rule, txn, hit=hit)
            results[rule.rule_id] = RuleEvaluation(hit=hit, formal_proof=formal_proof)
        return results

    def _evaluate_rule(self, rule: RuleDefinition, txn: TransactionModel) -> bool:
        all_ok = True
        if rule.all_of:
            all_ok = all(self._evaluate_condition_python(cond, txn) for cond in rule.all_of)
        any_ok = True
        if rule.any_of:
            any_ok = any(self._evaluate_condition_python(cond, txn) for cond in rule.any_of)
        return all_ok and any_ok

    def _evaluate_condition_python(self, cond: RuleCondition, txn: TransactionModel) -> bool:
        if cond.predicate == "is_weekend":
            return txn.timestamp.weekday() >= 5
        if not cond.field or not cond.op:
            return False

        value = getattr(txn, cond.field)
        target = cond.value
        if cond.op == "eq":
            return value == target
        if cond.op == "ne":
            return value != target
        if cond.op == "gt":
            return value > target
        if cond.op == "gte":
            return value >= target
        if cond.op == "lt":
            return value < target
        if cond.op == "lte":
            return value <= target
        if cond.op == "contains":
            return str(target) in str(value)
        return False

    def _build_formal_proof(self, rule: RuleDefinition, txn: TransactionModel, hit: bool) -> str:
        solver = Solver()
        z3_all: list[Any] = []
        z3_any: list[Any] = []

        for cond in rule.all_of:
            z3_all.append(self._evaluate_condition_z3(cond, txn))
        for cond in rule.any_of:
            z3_any.append(self._evaluate_condition_z3(cond, txn))

        all_expr = And(*z3_all) if z3_all else BoolVal(True)
        if z3_any:
            # "any_of" for the formal expression is satisfiable if at least one clause is true.
            any_expr = z3_any[0]
            for part in z3_any[1:]:
                any_expr = any_expr | part
        else:
            any_expr = BoolVal(True)

        expr = And(all_expr, any_expr)
        solver.add(expr if hit else ~expr)
        result = solver.check()
        return (
            f"z3_check={result}; "
            f"rule={rule.rule_id}; "
            f"expected_hit={hit}; "
            f"assertions={[str(a) for a in solver.assertions()]}"
        )

    def _evaluate_condition_z3(self, cond: RuleCondition, txn: TransactionModel) -> Any:
        if cond.predicate == "is_weekend":
            return BoolVal(txn.timestamp.weekday() >= 5)
        if not cond.field or not cond.op:
            return BoolVal(False)

        raw = getattr(txn, cond.field)
        if isinstance(raw, bool):
            left = BoolVal(raw)
            right = BoolVal(bool(cond.value))
            if cond.op == "eq":
                return left == right
            if cond.op == "ne":
                return left != right
            return BoolVal(False)

        try:
            left_num = RealVal(float(raw))
            right_num = RealVal(float(cond.value))
            if cond.op == "eq":
                return left_num == right_num
            if cond.op == "ne":
                return left_num != right_num
            if cond.op == "gt":
                return left_num > right_num
            if cond.op == "gte":
                return left_num >= right_num
            if cond.op == "lt":
                return left_num < right_num
            if cond.op == "lte":
                return left_num <= right_num
        except (TypeError, ValueError):
            pass
        return BoolVal(self._evaluate_condition_python(cond, txn))

    def _audit_log(self, rule: RuleDefinition, txn: TransactionModel, hit: bool) -> None:
        # RBI-safe log payload (hash IDs, avoid raw PAN/GSTIN leakage).
        digest = hashlib.sha256(f"{txn.account_id}:{txn.txn_id}".encode("utf-8")).hexdigest()[:16]
        logger.info(
            "layer1_rule_eval rule_id=%s category=%s severity=%s hit=%s txn_ref=%s ts=%s",
            rule.rule_id,
            rule.category,
            rule.severity,
            hit,
            digest,
            txn.timestamp.isoformat(),
        )


class KnowledgeGraph:
    """Account ↔ PAN ↔ GSTIN ↔ Device link graph."""

    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph()

    def add_transaction(self, txn: TransactionModel) -> None:
        account = f"account:{txn.account_id}"
        self.graph.add_node(account, kind="account")

        if txn.pan:
            pan = f"pan:{txn.pan}"
            self.graph.add_node(pan, kind="pan")
            self.graph.add_edge(account, pan, relation="has_pan")

        if txn.gstin:
            gstin = f"gstin:{txn.gstin}"
            self.graph.add_node(gstin, kind="gstin")
            self.graph.add_edge(account, gstin, relation="has_gstin")

        if txn.device_id:
            device = f"device:{txn.device_id}"
            self.graph.add_node(device, kind="device")
            self.graph.add_edge(account, device, relation="used_by")

        if txn.beneficiary_account:
            beneficiary = f"account:{txn.beneficiary_account}"
            self.graph.add_node(beneficiary, kind="account")
            self.graph.add_edge(account, beneficiary, relation="transfers_to")


class Layer1AuditPlugin:
    def __init__(self, rule_engine: RuleEngine, graph: KnowledgeGraph | None = None):
        self.rule_engine = rule_engine
        self.graph = graph or KnowledgeGraph()

    def audit_txn(self, txn_dict: dict[str, Any]) -> dict[str, Any]:
        txn = TransactionModel.model_validate(txn_dict)
        self.graph.add_transaction(txn)
        evals = self.rule_engine.evaluate(txn)

        hits = [rule_id for rule_id, outcome in evals.items() if outcome.hit]
        proof = {rule_id: outcome.formal_proof for rule_id, outcome in evals.items() if outcome.hit}
        return {
            "is_flagged": bool(hits),
            "rules_hit": hits,
            "proof": proof,
        }


def default_plugin() -> Layer1AuditPlugin:
    base = Path(__file__).resolve().parent / "rules" / "rbi_pmla_layer1_rules.json"
    return Layer1AuditPlugin(rule_engine=RuleEngine.from_json_file(base))
