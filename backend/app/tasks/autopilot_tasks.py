"""Scheduled Autopilot refresh tasks."""
from app.celery_app import celery_app
from app.database import SessionLocal, reset_current_org, set_current_org
from app.engines.autopilot_engine import refresh_autopilot_exceptions


@celery_app.task(queue="heavy")
def refresh_all_autopilot_inboxes():
    from app.models.organization import Organization

    db = SessionLocal()
    refreshed = []
    try:
        org_ids = [str(org.id) for org in db.query(Organization).all()]
        db.commit()
        for org_id in org_ids:
            token = set_current_org(org_id)
            try:
                result = refresh_autopilot_exceptions(db, org_id)
                refreshed.append({"org_id": org_id, **result})
                db.commit()
            finally:
                reset_current_org(token)
        return {"refreshed": refreshed}
    finally:
        db.close()
