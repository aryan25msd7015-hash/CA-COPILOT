"""Reconciliation Celery tasks - queue: heavy."""
import logging
from datetime import datetime, timezone

import pandas as pd

from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


def _period_bounds(period: str):
    for fmt in ("%b %Y", "%b-%Y", "%Y-%m"):
        try:
            start = pd.Timestamp(datetime.strptime(period, fmt))
            return start.date(), (start + pd.offsets.MonthEnd(1)).date()
        except ValueError:
            continue
    return None


def _set_failed(db, result_id: str | None, exc: Exception) -> None:
    if not result_id:
        return
    from app.models.reconciliation import ReconciliationResult

    result = db.query(ReconciliationResult).filter(ReconciliationResult.id == result_id).first()
    if result:
        result.status = "failed"
        result.error_message = str(exc)[:1000]
        result.completed_at = datetime.now(timezone.utc)
        db.commit()


@celery_app.task(bind=True, queue="heavy", max_retries=3,
                 autoretry_for=(Exception,), retry_backoff=True)
def run_reconciliation(self, client_id: str, period: str, result_id: str | None = None):
    """Run the 3-tier reconciliation for a client period."""
    from app.models.client import Client
    from app.models.transaction import Transaction
    from app.models.reconciliation import ReconciliationConfig, ReconciliationResult
    from app.engines.reconciliation_engine import reconcile
    from app.tasks.anomaly_tasks import run_anomaly_detection

    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            logger.error("Client %s not found", client_id)
            return {"matched": 0, "unmatched": 0, "error": "client_not_found"}

        result = db.query(ReconciliationResult).filter(ReconciliationResult.id == result_id).first() if result_id else None
        if result:
            result.status = "running"
            result.error_message = None
            db.commit()

        purchase_query = db.query(Transaction).filter(
            Transaction.org_id == client.org_id,
            Transaction.client_id == client_id,
            Transaction.source == "upload",
        )
        gstr2b_query = db.query(Transaction).filter(
            Transaction.org_id == client.org_id,
            Transaction.client_id == client_id,
            Transaction.source == "gstr2b",
        )
        bounds = _period_bounds(period)
        if bounds:
            purchase_query = purchase_query.filter(Transaction.date.between(*bounds))
            gstr2b_query = gstr2b_query.filter(Transaction.date.between(*bounds))
        purchase_rows = purchase_query.all()
        gstr2b_rows = gstr2b_query.all()

        def to_df(rows):
            return pd.DataFrame([{
                "id": str(r.id),
                "vendor_gstin": r.vendor_gstin,
                "invoice_no": r.invoice_no,
                "vendor_name": r.vendor_name,
                "amount": float(r.amount or 0),
                "date": r.date,
            } for r in rows])

        purchase_df = to_df(purchase_rows)
        gstr2b_df = to_df(gstr2b_rows)
        gstr2b_total = float(gstr2b_df["amount"].sum()) if not gstr2b_df.empty else 0.0

        if purchase_df.empty:
            logger.info("No purchase transactions for client %s period %s", client_id, period)
            if not result:
                result = ReconciliationResult(org_id=client.org_id, client_id=client_id, period=period)
                db.add(result)
            result.status = "completed"
            result.total_purchase = 0
            result.total_gstr2b = gstr2b_total
            result.matched_count = 0
            result.unmatched_count = 0
            result.mismatch_value = 0
            result.input_summary = {
                "purchase_count": 0,
                "gstr2b_count": len(gstr2b_rows),
                "purchase_total": 0,
                "gstr2b_total": gstr2b_total,
            }
            result.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {"matched": 0, "unmatched": 0, "period": period, "result_id": str(result.id)}

        if gstr2b_df.empty:
            for txn in purchase_rows:
                txn.match_status = "unmatched"
                txn.match_confidence = None
            total_val = float(purchase_df["amount"].sum())
            if not result:
                result = ReconciliationResult(org_id=client.org_id, client_id=client_id, period=period)
                db.add(result)
            result.status = "completed"
            result.total_purchase = total_val
            result.total_gstr2b = 0
            result.matched_count = 0
            result.unmatched_count = len(purchase_rows)
            result.mismatch_value = total_val
            result.input_summary = {
                "purchase_count": len(purchase_rows),
                "gstr2b_count": 0,
                "purchase_total": total_val,
                "gstr2b_total": 0,
                "matched_value": 0,
            }
            result.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {"matched": 0, "unmatched": len(purchase_rows), "period": period, "result_id": str(result.id)}

        cfg = db.query(ReconciliationConfig).filter(
            ReconciliationConfig.client_id == client_id
        ).first()
        config = {
            "amount_tolerance": float(cfg.amount_tolerance) if cfg else 5,
            "date_tolerance": int(cfg.date_tolerance) if cfg else 3,
            "fuzzy_threshold": int(cfg.fuzzy_threshold) if cfg else 85,
        }

        matched_df, unmatched_df = reconcile(purchase_df, gstr2b_df, config)

        for txn in purchase_rows:
            txn.match_status = "unmatched"
            txn.match_confidence = None

        purchase_by_id = {str(txn.id): txn for txn in purchase_rows}
        for _, row in matched_df.iterrows():
            txn = purchase_by_id.get(str(row["id"]))
            if txn:
                txn.match_status = row["match_type"]
                txn.match_confidence = row["confidence"]

        total_val = float(purchase_df["amount"].sum())
        matched_val = float(matched_df["amount"].sum()) if not matched_df.empty else 0.0
        if not result:
            result = ReconciliationResult(org_id=client.org_id, client_id=client_id, period=period)
            db.add(result)
        result.status = "completed"
        result.total_purchase = total_val
        result.total_gstr2b = gstr2b_total
        result.matched_count = len(matched_df)
        result.unmatched_count = len(unmatched_df)
        result.mismatch_value = total_val - matched_val
        result.input_summary = {
            "purchase_count": len(purchase_rows),
            "gstr2b_count": len(gstr2b_rows),
            "purchase_total": total_val,
            "gstr2b_total": gstr2b_total,
            "matched_value": matched_val,
        }
        result.completed_at = datetime.now(timezone.utc)
        db.commit()

        run_anomaly_detection.delay(client_id)

        return {
            "matched": len(matched_df),
            "unmatched": len(unmatched_df),
            "period": period,
            "result_id": str(result.id),
        }
    except Exception as exc:
        db.rollback()
        _set_failed(db, result_id, exc)
        raise
    finally:
        db.close()
