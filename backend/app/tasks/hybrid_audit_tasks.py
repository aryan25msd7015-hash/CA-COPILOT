"""Celery tasks for Hybrid Audit Engine training, scoring, and evaluation."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


def _persist_artifact_row(db, org_id, name: str, meta: dict | None):
    from app.models.audit_ml import AuditModelArtifact

    if not meta:
        return
    row = AuditModelArtifact(
        org_id=org_id,
        name=name,
        version=meta.get("version") or "latest",
        backend=str((meta.get("backend") or meta.get("metrics", {}).get("backend") or "sklearn")),
        local_path=meta.get("local_path"),
        s3_key=meta.get("s3_key"),
        metrics=meta,
        is_active=True,
    )
    db.add(row)


@celery_app.task(bind=True, queue="heavy", max_retries=1)
def train_hybrid_audit_models(self, org_id: str, client_id: str | None = None):
    """Train L2/L3/L4 artifacts for an organization."""
    from app.engines.hybrid_audit_engine import train_org_models
    from app.engines.temporal_transformer_engine import fit_temporal_model
    from app.engines.graph_fraud_engine import fit_graph_model
    from app.engines.audit_bandit import LinUCBBandit, save_bandit
    from app.engines import model_registry
    from app.models.transaction import Transaction
    from app.models.audit_ml import AuditEngineRun

    db = SessionLocal()
    try:
        classical = train_org_models(db, org_id, client_id=client_id)
        q = db.query(Transaction).filter(Transaction.org_id == org_id, Transaction.amount.isnot(None))
        if client_id:
            q = q.filter(Transaction.client_id == client_id)
        txns = q.all()
        tft = fit_temporal_model(txns, org_id=org_id)
        gnn = fit_graph_model(txns, org_id=org_id)
        bandit_meta = save_bandit(LinUCBBandit(), org_id)

        for name in (
            "hae_unsupervised",
            "hae_supervised_risk",
            "hae_meta_stacker",
            "hae_temporal_transformer",
            "hae_graph_sage",
            "hae_linucb_bandit",
        ):
            _persist_artifact_row(db, org_id, name, model_registry.load_metadata(org_id, name))

        summary = {
            "classical": classical,
            "temporal": tft,
            "graph": gnn,
            "bandit": bandit_meta,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }
        db.add(AuditEngineRun(
            org_id=org_id,
            client_id=client_id,
            run_type="train",
            status="completed",
            summary=summary,
        ))
        db.commit()
        return summary
    except Exception as exc:
        logger.exception("HAE train failed for org=%s", org_id)
        db.rollback()
        db.add(AuditEngineRun(
            org_id=org_id,
            client_id=client_id,
            run_type="train",
            status="failed",
            summary={"error": str(exc)},
        ))
        db.commit()
        raise
    finally:
        db.close()


@celery_app.task(bind=True, queue="heavy", max_retries=2,
                 autoretry_for=(Exception,), retry_backoff=True)
def run_hybrid_audit_scoring(self, client_id: str, org_id: str | None = None,
                             materiality_override: float | None = None):
    """Score a client with HAE-5 precision fusion + human-auditor assertions."""
    from app.models.transaction import Transaction
    from app.models.anomaly_flag import AnomalyFlag
    from app.models.audit_ml import AuditEngineRun
    from app.engines.temporal_transformer_engine import score_sequences
    from app.engines.graph_fraud_engine import score_graph
    from app.engines.hybrid_audit_engine import score_transactions
    from app.engines.anomaly_detector import benford_test, detect_vendor_spikes
    from app.engines.audit_assertions_engine import (
        run_assertion_procedures, assertion_scores_map, confidence_map,
    )
    from app.engines.audit_bandit import adaptive_sample_plan

    db = SessionLocal()
    try:
        txns = db.query(Transaction).filter(
            Transaction.client_id == client_id,
            Transaction.amount.isnot(None),
        ).all()
        if not txns:
            return {"flags": 0, "scored": 0}

        resolved_org = org_id or str(txns[0].org_id)

        db.query(AnomalyFlag).filter(
            AnomalyFlag.client_id == client_id,
            AnomalyFlag.reviewed.is_(False),
        ).delete(synchronize_session=False)

        assertion_result = run_assertion_procedures(
            txns, materiality_override=materiality_override
        )
        a_scores = assertion_scores_map(assertion_result)
        c_scores = confidence_map(assertion_result)
        a_payloads = assertion_result.get("transaction_assertions") or {}

        tft_scores = score_sequences(txns, org_id=resolved_org)
        gnn_scores = score_graph(txns, org_id=resolved_org)
        scored = score_transactions(
            txns,
            org_id=resolved_org,
            tft_scores=tft_scores,
            gnn_scores=gnn_scores,
            assertion_scores=a_scores,
            assertion_payloads=a_payloads,
            confidence_scores=c_scores,
        )

        txn_by_id = {str(t.id): t for t in txns}
        flags_created = 0
        high_risk = 0
        scored_rows = []
        for _, row in scored.iterrows():
            txn = txn_by_id.get(str(row["id"]))
            if not txn:
                continue
            prob = float(row["audit_risk_prob"])
            payload = a_payloads.get(str(row["id"])) or {}
            txn.anomaly_score = prob
            txn.audit_risk_prob = prob
            txn.audit_risk_score = float(row["audit_risk_score"])
            txn.audit_risk_drivers = row["drivers"]
            txn.audit_confidence = float(row.get("audit_confidence") or payload.get("confidence") or 0.5)
            txn.audit_assertions = {
                "failed_assertions": payload.get("failed_assertions") or [],
                "assertions": payload.get("assertions") or {},
                "evidence": payload.get("evidence") or row.get("evidence"),
            }
            txn.hae_layer_scores = {
                "rule": float(row["rule_score"]),
                "unsupervised": float(row["unsup_score"]),
                "supervised": float(row["sup_score"]),
                "temporal": float(row["tft_score"]),
                "graph": float(row["gnn_score"]),
                "assertion": float(row.get("assertion_score") or 0),
            }
            scored_rows.append({
                "id": str(txn.id),
                "amount": float(txn.amount or 0),
                "audit_risk_prob": prob,
                "drivers": row["drivers"],
                "failed_assertions": payload.get("failed_assertions") or [],
                "evidence": payload.get("evidence"),
            })

            if prob >= 0.6:
                high_risk += 1
                db.add(AnomalyFlag(
                    org_id=txn.org_id,
                    client_id=client_id,
                    transaction_id=txn.id,
                    flag_type="hybrid_fusion",
                    risk_score=prob,
                    details={
                        "amount": float(txn.amount or 0),
                        "vendor_gstin": txn.vendor_gstin,
                        "audit_risk_score": float(row["audit_risk_score"]),
                        "audit_confidence": float(txn.audit_confidence or 0),
                        "layers": txn.hae_layer_scores,
                        "drivers": row["drivers"],
                        "rule_flags": row["rule_flags"],
                        "failed_assertions": payload.get("failed_assertions") or [],
                        "evidence": payload.get("evidence"),
                        "recommended_procedures": (payload.get("evidence") or {}).get("recommended_procedures"),
                    },
                ))
                flags_created += 1

            # Typed assertion flags (human-auditor language)
            for assertion_name in payload.get("failed_assertions") or []:
                assertion_blob = (payload.get("assertions") or {}).get(assertion_name) or {}
                a_score = float(assertion_blob.get("score") or 0)
                if a_score < 0.55:
                    continue
                flag_type = {
                    "cutoff": "cutoff",
                    "completeness": "completeness",
                    "existence": "existence",
                    "classification": "classification",
                    "accuracy": "classification",
                    "related_party": "related_party",
                    "journal_entry": "journal_entry",
                    "three_way_match": "three_way_match",
                    "aging": "aging",
                }.get(assertion_name, assertion_name)[:30]
                db.add(AnomalyFlag(
                    org_id=txn.org_id,
                    client_id=client_id,
                    transaction_id=txn.id,
                    flag_type=flag_type,
                    risk_score=a_score,
                    details={
                        "assertion": assertion_name,
                        "detail": assertion_blob.get("detail"),
                        "evidence": payload.get("evidence"),
                        "amount": float(txn.amount or 0),
                    },
                ))
                flags_created += 1

            if float(row["tft_score"]) >= 0.75:
                db.add(AnomalyFlag(
                    org_id=txn.org_id,
                    client_id=client_id,
                    transaction_id=txn.id,
                    flag_type="temporal",
                    risk_score=float(row["tft_score"]),
                    details={"drivers": row["drivers"], "layer": "tft"},
                ))
                flags_created += 1
            if float(row["gnn_score"]) >= 0.75:
                db.add(AnomalyFlag(
                    org_id=txn.org_id,
                    client_id=client_id,
                    transaction_id=txn.id,
                    flag_type="graph_collusion",
                    risk_score=float(row["gnn_score"]),
                    details={"vendor_gstin": txn.vendor_gstin, "layer": "gnn"},
                ))
                flags_created += 1
            for rule_flag in row["rule_flags"] or []:
                risk_map = {
                    "round_number": 0.4,
                    "weekend": 0.3,
                    "duplicate": 0.9,
                    "threshold_gaming": 0.6,
                }
                db.add(AnomalyFlag(
                    org_id=txn.org_id,
                    client_id=client_id,
                    transaction_id=txn.id,
                    flag_type=rule_flag,
                    risk_score=risk_map.get(rule_flag, 0.5),
                    details={"amount": float(txn.amount or 0)},
                ))
                flags_created += 1

        amounts = [float(t.amount or 0) for t in txns]
        benford = benford_test(amounts)
        if benford.get("suspicious"):
            db.add(AnomalyFlag(
                org_id=txns[0].org_id,
                client_id=client_id,
                flag_type="benford",
                risk_score=0.8,
                details=benford,
            ))
            flags_created += 1

        for spike in detect_vendor_spikes(client_id, db):
            db.add(AnomalyFlag(
                org_id=txns[0].org_id,
                client_id=client_id,
                flag_type="vendor_spike",
                risk_score=0.7,
                details=spike,
            ))
            flags_created += 1

        mat = assertion_result.get("materiality") or {}
        sample = adaptive_sample_plan(
            scored_rows,
            materiality=float(mat.get("planning_materiality") or 100000),
            performance_materiality=float(mat.get("performance_materiality") or 75000),
            clearly_trivial=float(mat.get("clearly_trivial") or 3750),
            review_budget=25,
            org_id=resolved_org,
        )

        summary = {
            "engine": "HAE-5",
            "scored": len(scored),
            "flags": flags_created,
            "high_risk": high_risk,
            "benford": benford,
            "materiality": mat,
            "period_end": assertion_result.get("period_end"),
            "assertion_coverage": assertion_result.get("coverage"),
            "population": assertion_result.get("population"),
            "sample_plan": {
                "selected_count": sample.get("selected_count"),
                "population_coverage_pct": sample.get("population_coverage_pct"),
                "residual_high_risk_count": sample.get("residual_high_risk_count"),
                "stratum_counts": sample.get("stratum_counts"),
            },
        }
        db.add(AuditEngineRun(
            org_id=resolved_org,
            client_id=client_id,
            run_type="score",
            status="completed",
            summary=summary,
        ))
        db.commit()
        return summary
    finally:
        db.close()


@celery_app.task(queue="heavy")
def evaluate_hybrid_audit_models(org_id: str, client_id: str | None = None):
    """Offline evaluation harness using partner review labels."""
    from app.models.transaction import Transaction
    from app.models.audit_ml import AuditEngineRun
    from app.engines.hybrid_audit_engine import (
        labels_from_reviews,
        score_transactions,
    )
    from app.engines.temporal_transformer_engine import score_sequences
    from app.engines.graph_fraud_engine import score_graph
    import numpy as np

    db = SessionLocal()
    try:
        q = db.query(Transaction).filter(Transaction.org_id == org_id, Transaction.amount.isnot(None))
        if client_id:
            q = q.filter(Transaction.client_id == client_id)
        txns = q.all()
        label_map = labels_from_reviews(db, client_id=client_id, org_id=org_id)
        tft = score_sequences(txns, org_id=org_id)
        gnn = score_graph(txns, org_id=org_id)
        scored = score_transactions(txns, org_id=org_id, tft_scores=tft, gnn_scores=gnn)

        y_true, y_prob = [], []
        for _, row in scored.iterrows():
            tid = str(row["id"])
            if tid not in label_map:
                continue
            y_true.append(label_map[tid])
            y_prob.append(float(row["audit_risk_prob"]))

        metrics = {
            "labeled": len(y_true),
            "positives": int(sum(y_true)),
        }
        if y_true:
            y_true_a = np.asarray(y_true)
            y_prob_a = np.asarray(y_prob)
            order = np.argsort(-y_prob_a)
            top_k = max(1, min(20, len(order)))
            precision_at_k = float(y_true_a[order][:top_k].mean()) if top_k else 0.0
            preds = (y_prob_a >= 0.65).astype(int)
            tp = int(((preds == 1) & (y_true_a == 1)).sum())
            fp = int(((preds == 1) & (y_true_a == 0)).sum())
            fn = int(((preds == 0) & (y_true_a == 1)).sum())
            precision = tp / max(tp + fp, 1)
            recall = tp / max(tp + fn, 1)
            metrics.update({
                "precision_at_k": round(precision_at_k, 4),
                "k": top_k,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "fpr": round(fp / max(fp + int(((preds == 0) & (y_true_a == 0)).sum()), 1), 4),
            })

        db.add(AuditEngineRun(
            org_id=org_id,
            client_id=client_id,
            run_type="eval",
            status="completed",
            summary=metrics,
        ))
        db.commit()
        return metrics
    finally:
        db.close()


@celery_app.task(queue="heavy")
def train_all_org_hybrid_models():
    """Nightly beat entrypoint: train HAE models for every organization."""
    from app.models.organization import Organization

    db = SessionLocal()
    try:
        org_ids = [str(o.id) for o in db.query(Organization).all()]
    finally:
        db.close()

    results = []
    for org_id in org_ids:
        try:
            results.append({"org_id": org_id, **train_hybrid_audit_models.run(org_id)})
        except Exception as exc:
            logger.exception("Nightly HAE train failed for %s", org_id)
            results.append({"org_id": org_id, "error": str(exc)})
    return {"orgs": len(org_ids), "results": results}