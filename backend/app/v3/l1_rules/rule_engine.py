"""v3.0 Layer-1 RuleEngine with Z3 proof output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from z3 import And, BoolVal, RealVal, Solver


class RuleCondition(BaseModel):
    field: str | None = None
    op: Literal["gt", "gte", "lt", "lte", "eq", "ne"] | None = None
    value: float | bool | str | None = None
    predicate: Literal["is_weekend"] | None = None


class RuleDefinition(BaseModel):
    rule_id: str
    title: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    all_of: list[RuleCondition] = Field(default_factory=list)

    @field_validator("rule_id")
    @classmethod
    def validate_rule_id(cls, value: str) -> str:
        clean = value.strip().lower()
        if not clean:
            raise ValueError("rule_id is required")
        return clean


class TxnModel(BaseModel):
    txn_id: str
    amount: float = Field(gt=0)
    timestamp: datetime
    txn_count_24h: int = 0
    total_amount_24h: float = 0.0
    is_new_beneficiary: bool = False
    is_international: bool = False
    pan_gstin_mismatch: bool = False

    @field_validator("timestamp")
    @classmethod
    def normalize_ts(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


@dataclass
class RuleResult:
    hit: bool
    formal_proof: str


class RuleEngine:
    def __init__(self, rules: list[RuleDefinition]):
        self.rules = rules

    @classmethod
    def from_json(cls, path: str | Path) -> "RuleEngine":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([RuleDefinition.model_validate(item) for item in payload])

    def evaluate(self, txn: TxnModel) -> dict[str, RuleResult]:
        out: dict[str, RuleResult] = {}
        for rule in self.rules:
            hit = all(self._eval_cond(cond, txn) for cond in rule.all_of)
            out[rule.rule_id] = RuleResult(
                hit=hit,
                formal_proof=self._proof(rule, txn, hit),
            )
        return out

    def audit_txn(self, txn_dict: dict[str, Any]) -> dict[str, Any]:
        txn = TxnModel.model_validate(txn_dict)
        results = self.evaluate(txn)
        rules_hit = [rid for rid, result in results.items() if result.hit]
        return {
            "is_flagged": bool(rules_hit),
            "rules_hit": rules_hit,
            "proof": {rid: result.formal_proof for rid, result in results.items()},
        }

    def _eval_cond(self, cond: RuleCondition, txn: TxnModel) -> bool:
        if cond.predicate == "is_weekend":
            return txn.timestamp.weekday() >= 5
        if not cond.field or not cond.op:
            return False
        left = getattr(txn, cond.field)
        right = cond.value
        if cond.op == "gt":
            return left > right
        if cond.op == "gte":
            return left >= right
        if cond.op == "lt":
            return left < right
        if cond.op == "lte":
            return left <= right
        if cond.op == "eq":
            return left == right
        if cond.op == "ne":
            return left != right
        return False

    def _proof(self, rule: RuleDefinition, txn: TxnModel, hit: bool) -> str:
        solver = Solver()
        exprs = [self._z3_expr(cond, txn) for cond in rule.all_of]
        combined = And(*exprs) if exprs else BoolVal(True)
        solver.add(combined if hit else ~combined)
        check = solver.check()
        return (
            f"z3_check={check}; rule={rule.rule_id}; expected_hit={hit}; "
            f"assertions={[str(a) for a in solver.assertions()]}"
        )

    def _z3_expr(self, cond: RuleCondition, txn: TxnModel) -> Any:
        if cond.predicate == "is_weekend":
            return BoolVal(txn.timestamp.weekday() >= 5)
        if not cond.field or not cond.op:
            return BoolVal(False)
        left_raw = getattr(txn, cond.field)
        if isinstance(left_raw, bool):
            left = BoolVal(left_raw)
            right = BoolVal(bool(cond.value))
            if cond.op == "eq":
                return left == right
            if cond.op == "ne":
                return left != right
            return BoolVal(False)
        try:
            left_num = RealVal(float(left_raw))
            right_num = RealVal(float(cond.value))
            if cond.op == "gt":
                return left_num > right_num
            if cond.op == "gte":
                return left_num >= right_num
            if cond.op == "lt":
                return left_num < right_num
            if cond.op == "lte":
                return left_num <= right_num
            if cond.op == "eq":
                return left_num == right_num
            if cond.op == "ne":
                return left_num != right_num
        except (TypeError, ValueError):
            return BoolVal(self._eval_cond(cond, txn))
        return BoolVal(False)
