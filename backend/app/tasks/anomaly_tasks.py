"""Anomaly detection Celery tasks — queue: heavy"""
import logging
import pandas as pd
from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(queue="heavy")
def run_invoice_fraud_scan(transaction_id: str):
    from app.engines.invoice_fraud_scanner import scan_invoice
    db = SessionLocal()
    try:
        return scan_invoice(transaction_id, db)
    finally:
        db.close()


@celery_app.task(bind=True, queue="heavy", max_retries=2,
                 autoretry_for=(Exception,), retry_backoff=True)
def run_anomaly_detection(self, client_id: str):
    """Full anomaly detection pipeline for a client."""
    from app.models.transaction import Transaction
    from app.models.anomaly_flag import AnomalyFlag
    from app.engines.anomaly_detector import (
        train_isolation_forest, score_transaction,
        benford_test, flag_rule_anomalies, detect_vendor_spikes,
    )

    db = SessionLocal()
    try:
        db.query(AnomalyFlag).filter(
            AnomalyFlag.client_id == client_id,
            AnomalyFlag.reviewed.is_(False),
        ).delete(synchronize_session=False)

        txns = db.query(Transaction).filter(
            Transaction.client_id == client_id,
            Transaction.amount.isnot(None),
        ).all()

        if not txns:
            return {"flags": 0}

        df = pd.DataFrame([{
            "id": str(t.id), "vendor_gstin": t.vendor_gstin or "",
            "invoice_no": t.invoice_no or "", "amount": float(t.amount),
            "date": t.date, "org_id": str(t.org_id),
        } for t in txns])

        # 1. Isolation Forest
        model, stats_df = train_isolation_forest(df)
        for _, row in df.iterrows():
            txn = db.query(Transaction).filter(Transaction.id == row["id"]).first()
            if txn:
                score = score_transaction(
                    model, stats_df, row["vendor_gstin"], row["amount"]
                )
                txn.anomaly_score = score
                if score >= 0.7:
                    db.add(AnomalyFlag(
                        org_id=txn.org_id,
                        client_id=client_id,
                        transaction_id=txn.id,
                        flag_type="isolation_forest",
                        risk_score=score,
                        details={"amount": row["amount"], "vendor_gstin": row["vendor_gstin"]},
                    ))

        # 2. Benford test (dataset-level flag)
        benford = benford_test(df["amount"].tolist())
        if benford.get("suspicious"):
            flag = AnomalyFlag(
                org_id=txns[0].org_id, client_id=client_id,
                flag_type="benford",
                risk_score=0.8,
                details=benford,
            )
            db.add(flag)

        # 3. Rule-based flags (per transaction)
        df = flag_rule_anomalies(df)
        flag_cols = {
            "flag_round":     ("round_number", 0.4),
            "flag_weekend":   ("weekend",      0.3),
            "flag_duplicate": ("duplicate",    0.9),
            "flag_threshold": ("threshold_gaming", 0.6),
        }
        for col, (flag_type, risk) in flag_cols.items():
            for _, row in df[df[col]].iterrows():
                flag = AnomalyFlag(
                    org_id=txns[0].org_id, client_id=client_id,
                    transaction_id=row["id"],
                    flag_type=flag_type,
                    risk_score=risk,
                    details={"amount": row["amount"], "date": str(row.get("date", ""))},
                )
                db.add(flag)

        # 4. Vendor spikes
        spikes = detect_vendor_spikes(client_id, db)
        for spike in spikes:
            flag = AnomalyFlag(
                org_id=txns[0].org_id, client_id=client_id,
                flag_type="vendor_spike", risk_score=0.7, details=spike,
            )
            db.add(flag)

        db.commit()
        return {"flags": len(db.query(AnomalyFlag).filter(
            AnomalyFlag.client_id == client_id).all())}
    finally:
        db.close()
