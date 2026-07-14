from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.autopilot import AutopilotSyncRun
from app.models.document import Document
from app.models.system import SystemEvent
from app.models.whatsapp_reminder import WhatsAppReminder
from app.services.email_service import email_provider_status
from app.services.observability import observability_status
from app.services.payment_gateway import payment_gateway_status
from app.utils.deps import get_current_user
from app.utils.scoped_query import scoped

router = APIRouter()


def _configured(*values: str) -> bool:
    return all(bool(value) for value in values)


def _status(configured: bool, failures: int = 0) -> str:
    if not configured:
        return "dev_fallback"
    if failures:
        return "degraded"
    return "ready"


@router.get("/health")
def integration_health(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    org_id = request.state.org_id
    wa_failures = scoped(db, WhatsAppReminder, org_id).filter(WhatsAppReminder.status == "failed").count()
    wa_total = scoped(db, WhatsAppReminder, org_id).count()
    latest_wa = scoped(db, WhatsAppReminder, org_id).order_by(WhatsAppReminder.sent_at.desc()).first()

    failed_docs = scoped(db, Document, org_id).filter(Document.status.in_(["ocr_failed", "parse_failed", "failed_validation"])).count()
    latest_doc = scoped(db, Document, org_id).order_by(Document.created_at.desc()).first()

    tally_failed = scoped(db, AutopilotSyncRun, org_id).filter(
        AutopilotSyncRun.status.in_(["failed", "completed_with_errors"])
    ).count()
    tally_total = scoped(db, AutopilotSyncRun, org_id).count()
    latest_tally = scoped(db, AutopilotSyncRun, org_id).order_by(AutopilotSyncRun.started_at.desc()).first()

    event_failures = scoped(db, SystemEvent, org_id).filter(SystemEvent.status == "failed").count()
    events_recorded = scoped(db, SystemEvent, org_id).count()
    email_status = email_provider_status()
    payment_status = payment_gateway_status()
    obs_status = observability_status()

    payload = {
        "organization_id": str(org_id),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "integrations": {
            "whatsapp": {
                "status": _status(_configured(settings.WHATSAPP_TOKEN, settings.WHATSAPP_PHONE_ID), wa_failures),
                "configured": _configured(settings.WHATSAPP_TOKEN, settings.WHATSAPP_PHONE_ID),
                "mode": "meta_business_api" if _configured(settings.WHATSAPP_TOKEN, settings.WHATSAPP_PHONE_ID) else "development_fallback",
                "messages_total": wa_total,
                "messages_failed": wa_failures,
                "last_status": latest_wa.status if latest_wa else None,
                "last_error": latest_wa.error_message if latest_wa and latest_wa.status == "failed" else None,
            },
            "ocr": {
                "status": _status(_configured(settings.AZURE_DOC_ENDPOINT, settings.AZURE_DOC_KEY), failed_docs),
                "configured": _configured(settings.AZURE_DOC_ENDPOINT, settings.AZURE_DOC_KEY),
                "mode": "azure_document_intelligence" if _configured(settings.AZURE_DOC_ENDPOINT, settings.AZURE_DOC_KEY) else "local_placeholder",
                "failed_documents": failed_docs,
                "last_document_status": latest_doc.status if latest_doc else None,
                "last_error_type": latest_doc.last_pipeline_error_type if latest_doc else None,
            },
            "storage": {
                "status": _status(_configured(settings.S3_BUCKET, settings.AWS_REGION)),
                "configured": _configured(settings.S3_BUCKET, settings.AWS_REGION),
                "bucket": settings.S3_BUCKET,
                "region": settings.AWS_REGION,
            },
            "ai": {
                "status": _status(_configured(settings.ANTHROPIC_API_KEY) or _configured(settings.OPENAI_API_KEY)),
                "anthropic_configured": bool(settings.ANTHROPIC_API_KEY),
                "openai_configured": bool(settings.OPENAI_API_KEY),
                "mode": "llm_enabled" if settings.ANTHROPIC_API_KEY or settings.OPENAI_API_KEY else "deterministic_fallback",
            },
            "email": {
                "status": _status(bool(email_status["configured"])),
                **email_status,
            },
            "payments": {
                "status": _status(bool(payment_status["configured"])),
                **payment_status,
            },
            "observability": {
                "status": _status(bool(obs_status["sentry_configured"] or obs_status["metrics_enabled"])),
                "configured": bool(obs_status["sentry_configured"] or obs_status["metrics_enabled"]),
                "mode": "sentry_and_prometheus" if obs_status["sentry_configured"] and obs_status["metrics_enabled"] else "metrics_only" if obs_status["metrics_enabled"] else "not_configured",
                **obs_status,
            },
            "tally": {
                "status": _status(True, tally_failed),
                "configured": True,
                "mode": "authenticated_json_connector",
                "sync_runs_total": tally_total,
                "sync_runs_failed": tally_failed,
                "last_status": latest_tally.status if latest_tally else None,
                "last_records_imported": latest_tally.records_imported if latest_tally else None,
            },
            "event_orchestration": {
                "status": _status(True, event_failures),
                "configured": True,
                "events_recorded": events_recorded,
                "events_failed": event_failures,
            },
        },
        "summary": {"ready": 0, "degraded": 0, "dev_fallback": 0},
    }
    for item in payload["integrations"].values():
        payload["summary"][item["status"]] += 1
    return payload
