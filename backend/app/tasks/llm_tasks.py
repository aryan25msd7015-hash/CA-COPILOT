"""LLM-backed notice, audit-paper, and natural-language query tasks."""
import io
import base64
from datetime import datetime, timezone

import pandas as pd

from app.celery_app import celery_app
from app.database import SessionLocal


@celery_app.task(bind=True, queue="llm", max_retries=2, retry_backoff=True)
def generate_notice_draft(self, document_id: str):
    from app.config import settings
    from app.engines.rag_drafter import (
        draft_reply, draft_reply_fallback, draft_reply_openai, parse_notice, retrieve_legal_context,
    )
    from app.models.document import Document

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError("Document not found")
        notice_data = parse_notice(doc.ocr_text or "")
        try:
            chunks = retrieve_legal_context(doc.ocr_text or "", db)
        except Exception:
            chunks = []
        result = None
        doc.ocr_json = {
            **(doc.ocr_json or {}),
            "notice_data": notice_data,
            "draft_status": "generating",
            "draft_started_at": datetime.now(timezone.utc).isoformat(),
        }
        db.commit()

        try:
            if settings.ANTHROPIC_API_KEY:
                from anthropic import Anthropic

                result = draft_reply(notice_data, chunks, Anthropic(api_key=settings.ANTHROPIC_API_KEY))
                result["provider"] = "anthropic"
            elif settings.OPENAI_API_KEY:
                from openai import OpenAI

                result = draft_reply_openai(notice_data, chunks, OpenAI(api_key=settings.OPENAI_API_KEY))
                result["provider"] = "openai"
        except Exception:
            result = draft_reply_fallback(notice_data, chunks)
        if result is None:
            result = draft_reply_fallback(notice_data, chunks)

        doc.ocr_json = {
            **(doc.ocr_json or {}),
            "notice_data": notice_data,
            "draft_status": "ready",
            "draft_completed_at": datetime.now(timezone.utc).isoformat(),
            "draft_error": None,
            "draft_result": result,
        }
        doc.status = "processed"
        db.commit()
        return result
    except Exception as exc:
        if "doc" in locals() and doc:
            doc.ocr_json = {
                **(doc.ocr_json or {}),
                "draft_status": "failed",
                "draft_completed_at": datetime.now(timezone.utc).isoformat(),
                "draft_error": str(exc)[:500],
            }
            db.commit()
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(bind=True, queue="llm", max_retries=2, retry_backoff=True)
def generate_audit_papers(self, document_id: str, period: str = "Current period"):
    from app.config import settings
    from app.engines.audit_papers_engine import (
        compute_ratios, export_working_paper, generate_audit_observations,
        generate_audit_observations_fallback, parse_trial_balance,
    )
    from app.models.anomaly_flag import AnomalyFlag
    from app.models.document import Document
    from app.services.s3_service import download_bytes, upload_bytes

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError("Document not found")
        doc.ocr_json = {
            **(doc.ocr_json or {}),
            "audit_status": "generating",
            "audit_started_at": datetime.now(timezone.utc).isoformat(),
            "audit_error": None,
        }
        db.commit()
        raw = None
        try:
            raw = download_bytes(doc.s3_key)
        except Exception:
            raw = None
        if raw is None and (doc.ocr_json or {}).get("trial_balance_rows"):
            frame = pd.DataFrame((doc.ocr_json or {}).get("trial_balance_rows"))
        elif raw is None:
            raise ValueError("Trial balance source file is unavailable")
        elif doc.s3_key.lower().endswith(".xlsx"):
            frame = pd.read_excel(io.BytesIO(raw))
        else:
            frame = pd.read_csv(io.BytesIO(raw))
        tb = parse_trial_balance(frame)
        ratios = compute_ratios(tb)
        anomalies = [
            {"type": a.flag_type, "risk_score": float(a.risk_score or 0), "details": a.details}
            for a in db.query(AnomalyFlag).filter(AnomalyFlag.client_id == doc.client_id).limit(20)
        ]
        provider = "deterministic_fallback"
        try:
            if settings.ANTHROPIC_API_KEY:
                from anthropic import Anthropic

                observations = generate_audit_observations(
                    tb, ratios, anomalies, Anthropic(api_key=settings.ANTHROPIC_API_KEY)
                )
                provider = "anthropic"
            else:
                observations = generate_audit_observations_fallback(tb, ratios, anomalies)
        except Exception:
            observations = generate_audit_observations_fallback(tb, ratios, anomalies)
            provider = "deterministic_fallback"
        output_key = f"{doc.org_id}/{doc.client_id}/audit-papers/{doc.id}.docx"
        output = export_working_paper(doc.client.name, observations, ratios, period)
        export_mode = "s3"
        try:
            upload_bytes(output_key, output, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            docx_base64 = None
        except Exception:
            export_mode = "metadata_base64"
            docx_base64 = base64.b64encode(output).decode()
        result = {
            "ratios": ratios,
            "observations": observations,
            "s3_key": output_key if export_mode == "s3" else None,
            "docx_base64": docx_base64,
            "provider": provider,
            "export_mode": export_mode,
            "period": period,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        doc.ocr_json = {
            **(doc.ocr_json or {}),
            "audit_status": "ready",
            "audit_completed_at": datetime.now(timezone.utc).isoformat(),
            "audit_error": None,
            "audit_result": result,
        }
        doc.status = "processed"
        db.commit()
        return result
    except Exception as exc:
        if "doc" in locals() and doc:
            doc.ocr_json = {
                **(doc.ocr_json or {}),
                "audit_status": "failed",
                "audit_completed_at": datetime.now(timezone.utc).isoformat(),
                "audit_error": str(exc)[:500],
            }
            db.commit()
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(bind=True, queue="llm", max_retries=2, retry_backoff=True)
def run_nl_query(self, question: str, org_id: str):
    from app.config import settings
    from app.engines.nl_query_engine import execute_query, translate_to_sql, translate_to_sql_fallback

    db = SessionLocal()
    try:
        provider = "deterministic_fallback"
        try:
            if settings.ANTHROPIC_API_KEY:
                from anthropic import Anthropic

                sql = translate_to_sql(question, org_id, Anthropic(api_key=settings.ANTHROPIC_API_KEY))
                provider = "anthropic"
            else:
                sql = translate_to_sql_fallback(question)
        except Exception:
            sql = translate_to_sql_fallback(question)
        result = execute_query(sql, org_id, db)
        result["provider"] = provider
        result["question"] = question
        return result
    except Exception as exc:
        raise self.retry(exc=exc)
    finally:
        db.close()
