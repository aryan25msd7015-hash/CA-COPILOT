"""Layer-4 AI auditor agent with LangGraph, PPO feedback, and fraud simulation."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger("banking_compliance.layer4")

try:
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - optional dependency at runtime
    END = "__end__"  # type: ignore[assignment]
    START = "__start__"  # type: ignore[assignment]
    StateGraph = None  # type: ignore[assignment]


class InvestigationInput(BaseModel):
    txn_id: str
    account_id: str
    amount: float = Field(gt=0)
    l1_output: dict[str, Any] = Field(default_factory=dict)
    l2_output: dict[str, Any] = Field(default_factory=dict)
    l3_output: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    tool_name: str
    payload: dict[str, Any]
    result: dict[str, Any]
    called_at: str


class InvestigationResult(BaseModel):
    final_risk: Literal["low", "medium", "high", "critical"]
    remark: str
    evidence_pack: dict[str, Any]


@dataclass
class AuditorPolicyLearner:
    """PPO wrapper: reward +10 on approval, -5 on rejection."""

    model: Any | None = None
    reward_history: list[float] = field(default_factory=list)
    learning_steps: int = 0

    def ensure_model(self) -> None:
        if self.model is not None:
            return
        try:
            import gymnasium as gym
            from gymnasium import spaces
            from stable_baselines3 import PPO
            from stable_baselines3.common.vec_env import DummyVecEnv
        except Exception as exc:  # pragma: no cover - dependency optional in minimal runs
            logger.debug("PPO dependencies unavailable: %s", exc)
            return

        class AuditorRewardEnv(gym.Env):
            action_space = spaces.Discrete(4)
            observation_space = spaces.Box(low=0.0, high=1.0, shape=(6,), dtype=np.float32)

            def __init__(self):
                super().__init__()
                self._state = np.zeros(6, dtype=np.float32)

            def reset(self, *, seed: int | None = None, options: dict | None = None):
                super().reset(seed=seed)
                self._state = np.random.default_rng(seed).random(6, dtype=np.float32)
                return self._state, {}

            def step(self, action: int):
                approved = float(self._state.mean() + (action * 0.03)) > 0.58
                reward = 10.0 if approved else -5.0
                self._state = np.random.default_rng().random(6, dtype=np.float32)
                terminated = True
                truncated = False
                return self._state, reward, terminated, truncated, {"approved": approved}

        vec = DummyVecEnv([lambda: AuditorRewardEnv()])
        self.model = PPO("MlpPolicy", vec, verbose=0, n_steps=16, batch_size=16, seed=42)

    def apply_feedback(self, approved: bool) -> float:
        reward = 10.0 if approved else -5.0
        self.reward_history.append(reward)
        self.ensure_model()
        if self.model is not None:
            self.model.learn(total_timesteps=16, progress_bar=False)
            self.learning_steps += 16
        return reward


@dataclass
class FraudSimulator:
    """Small GAN-style synthetic fraud transaction generator."""

    latent_dim: int = 8
    hidden_dim: int = 16
    seed: int = 42
    _generator: Any | None = None
    _discriminator: Any | None = None
    _torch: Any | None = None

    def __post_init__(self) -> None:
        try:
            import torch
            import torch.nn as nn

            self._torch = torch
            self._generator = nn.Sequential(
                nn.Linear(self.latent_dim, self.hidden_dim),
                nn.ReLU(),
                nn.Linear(self.hidden_dim, 3),
                nn.Sigmoid(),
            )
            self._discriminator = nn.Sequential(
                nn.Linear(3, self.hidden_dim),
                nn.ReLU(),
                nn.Linear(self.hidden_dim, 1),
                nn.Sigmoid(),
            )
        except Exception as exc:  # pragma: no cover - fallback path
            logger.debug("Torch unavailable for FraudSimulator GAN: %s", exc)

    def generate(self, n_samples: int = 8) -> list[dict[str, Any]]:
        rng = np.random.default_rng(self.seed + n_samples)
        if self._torch is None or self._generator is None:
            return [
                {
                    "synthetic_id": f"sim-{i}",
                    "amount": round(float(rng.uniform(250000, 2500000)), 2),
                    "velocity_risk": round(float(rng.uniform(0.45, 0.99)), 4),
                    "cross_border_risk": round(float(rng.uniform(0.35, 0.95)), 4),
                }
                for i in range(n_samples)
            ]

        torch = self._torch
        with torch.inference_mode():
            noise = torch.randn(n_samples, self.latent_dim)
            generated = self._generator(noise).detach().cpu().numpy()
        rows: list[dict[str, Any]] = []
        for i, vec in enumerate(generated):
            rows.append(
                {
                    "synthetic_id": f"sim-{i}",
                    "amount": round(float(150000 + (vec[0] * 2500000)), 2),
                    "velocity_risk": round(float(vec[1]), 4),
                    "cross_border_risk": round(float(vec[2]), 4),
                }
            )
        return rows

    def nightly_generate(self, batch_size: int = 32) -> dict[str, Any]:
        rows = self.generate(n_samples=batch_size)
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "batch_size": batch_size,
            "synthetic_transactions": rows,
        }


class AgentState(TypedDict):
    txn: dict[str, Any]
    l1: dict[str, Any]
    l2: dict[str, Any]
    l3: dict[str, Any]
    planned_tools: list[str]
    evidence_pack: dict[str, Any]
    final_risk: str
    remark: str


class Layer4AIAuditorAgent:
    """LangGraph ReAct-style auditor with audit-logged tool calls."""

    def __init__(self) -> None:
        self.policy = AuditorPolicyLearner()
        self.simulator = FraudSimulator()
        self.audit_trail: list[ToolCallRecord] = []
        self._graph = self._build_graph()

    # --- Tools ---
    def check_gstin(self, gstin: str | None) -> dict[str, Any]:
        gstin_clean = (gstin or "").strip().upper()
        valid = len(gstin_clean) == 15 and gstin_clean[:2].isdigit()
        result = {"gstin": gstin_clean or None, "valid": valid, "risk_delta": 0.0 if valid else 0.16}
        self._log_tool_call("check_gstin", {"gstin": gstin}, result)
        return result

    def check_sanctions(self, account_id: str) -> dict[str, Any]:
        blocked = account_id.upper().endswith(("X", "9"))
        result = {"account_id": account_id, "sanctions_hit": blocked, "risk_delta": 0.55 if blocked else 0.0}
        self._log_tool_call("check_sanctions", {"account_id": account_id}, result)
        return result

    def get_account_360(self, account_id: str) -> dict[str, Any]:
        rng = random.Random(hash(account_id) % 10000)
        profile = {
            "account_id": account_id,
            "kyc_score": round(rng.uniform(0.45, 0.98), 4),
            "chargeback_count_90d": rng.randint(0, 6),
            "linked_devices": rng.randint(1, 5),
            "avg_txn_30d": round(rng.uniform(15000, 600000), 2),
        }
        profile["risk_delta"] = min(0.25, (profile["chargeback_count_90d"] * 0.03) + ((profile["linked_devices"] - 1) * 0.02))
        self._log_tool_call("get_account_360", {"account_id": account_id}, profile)
        return profile

    def draft_remark(self, risk_label: str, reasoning: str, evidence: dict[str, Any]) -> dict[str, Any]:
        snippet = ", ".join(sorted(evidence.keys())[:4])
        remark = (
            f"AI Auditor assessment: {risk_label.upper()} risk. "
            f"{reasoning} Evidence anchors: {snippet or 'none'}."
        )
        result = {"remark": remark}
        self._log_tool_call(
            "draft_remark",
            {"risk_label": risk_label, "reasoning": reasoning, "evidence_keys": list(evidence.keys())},
            result,
        )
        return result

    # --- Public contract ---
    def investigate(self, txn: dict[str, Any]) -> dict[str, Any]:
        payload = InvestigationInput.model_validate(txn)
        initial: AgentState = {
            "txn": payload.model_dump(),
            "l1": payload.l1_output,
            "l2": payload.l2_output,
            "l3": payload.l3_output,
            "planned_tools": [],
            "evidence_pack": {
                "l1": payload.l1_output,
                "l2": payload.l2_output,
                "l3": payload.l3_output,
                "tool_calls": [],
            },
            "final_risk": "medium",
            "remark": "",
        }
        if self._graph is None:
            state = self._fallback_react(initial)
        else:
            state = self._graph.invoke(initial)

        result = InvestigationResult(
            final_risk=state["final_risk"],  # type: ignore[arg-type]
            remark=state["remark"],
            evidence_pack=state["evidence_pack"],
        )
        return result.model_dump()

    def apply_ca_feedback(self, approved: bool) -> dict[str, Any]:
        reward = self.policy.apply_feedback(approved=approved)
        return {
            "approved": approved,
            "reward": reward,
            "learning_steps": self.policy.learning_steps,
            "reward_history_tail": self.policy.reward_history[-10:],
        }

    def run_nightly_fraud_simulation(self, batch_size: int = 32) -> dict[str, Any]:
        return self.simulator.nightly_generate(batch_size=batch_size)

    # --- LangGraph/ReAct internals ---
    def _build_graph(self):
        if StateGraph is None:
            return None
        graph = StateGraph(AgentState)
        graph.add_node("plan", self._plan)
        graph.add_node("act", self._act)
        graph.add_node("finalize", self._finalize)
        graph.add_edge(START, "plan")
        graph.add_edge("plan", "act")
        graph.add_edge("act", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    def _plan(self, state: AgentState) -> AgentState:
        planned: list[str] = ["get_account_360"]
        txn = state["txn"]
        if txn.get("metadata", {}).get("gstin") or state["l1"].get("graph_summary"):
            planned.append("check_gstin")
        if state["l3"].get("ring_summary", {}).get("rings_detected", 0) or float(txn.get("amount", 0)) > 1_000_000:
            planned.append("check_sanctions")
        state["planned_tools"] = planned
        return state

    def _act(self, state: AgentState) -> AgentState:
        txn = state["txn"]
        evidence = dict(state["evidence_pack"])
        for tool_name in state["planned_tools"]:
            if tool_name == "get_account_360":
                evidence["account_360"] = self.get_account_360(str(txn["account_id"]))
            elif tool_name == "check_gstin":
                gstin = txn.get("metadata", {}).get("gstin")
                evidence["gstin_check"] = self.check_gstin(gstin)
            elif tool_name == "check_sanctions":
                evidence["sanctions_check"] = self.check_sanctions(str(txn["account_id"]))
        evidence["tool_calls"] = [record.model_dump() for record in self.audit_trail[-len(state["planned_tools"]) :]]
        state["evidence_pack"] = evidence
        return state

    def _finalize(self, state: AgentState) -> AgentState:
        l1_risk = float(state["l1"].get("risk_score", 0.0))
        l2_risk = float(state["l2"].get("risk_probability", state["l2"].get("summary", {}).get("avg_risk_probability", 0.0)))
        l3_risk = float(state["l3"].get("predicted_7d_risk", 0.0))
        tool_delta = 0.0
        for key in ("gstin_check", "sanctions_check", "account_360"):
            if key in state["evidence_pack"]:
                tool_delta += float(state["evidence_pack"][key].get("risk_delta", 0.0))
        score = min(1.0, max(0.0, (0.32 * l1_risk) + (0.28 * l2_risk) + (0.30 * l3_risk) + (0.10 * min(tool_delta, 1.0))))
        if score >= 0.85:
            label = "critical"
        elif score >= 0.65:
            label = "high"
        elif score >= 0.35:
            label = "medium"
        else:
            label = "low"
        reasoning = (
            f"Composite score={score:.2f} from L1={l1_risk:.2f}, L2={l2_risk:.2f}, "
            f"L3={l3_risk:.2f}, tool_delta={tool_delta:.2f}."
        )
        remark = self.draft_remark(label, reasoning, state["evidence_pack"])["remark"]
        state["final_risk"] = label
        state["remark"] = remark
        state["evidence_pack"]["composite_score"] = round(score, 4)
        return state

    def _fallback_react(self, state: AgentState) -> AgentState:
        state = self._plan(state)
        state = self._act(state)
        return self._finalize(state)

    def _log_tool_call(self, tool_name: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
        record = ToolCallRecord(
            tool_name=tool_name,
            payload=payload,
            result=result,
            called_at=datetime.now(UTC).isoformat(),
        )
        self.audit_trail.append(record)
        logger.info(
            "layer4_tool_call tool=%s payload=%s result=%s at=%s",
            record.tool_name,
            record.payload,
            record.result,
            record.called_at,
        )
