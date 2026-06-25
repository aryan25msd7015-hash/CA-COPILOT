"""Health score Celery tasks — queue: heavy"""
from app.celery_app import celery_app
from app.database import SessionLocal


@celery_app.task(queue="heavy")
def recompute_all_health_scores():
    """Nightly recompute for all clients — runs via Celery Beat at 02:00 IST."""
    from app.models.client import Client
    from app.models.health_history import ClientHealthHistory
    from app.engines.health_score_engine import compute_health_score

    db = SessionLocal()
    try:
        clients = db.query(Client).all()
        for client in clients:
            try:
                result = compute_health_score(str(client.id), db)
                client.health_score = result["score"]
                history = ClientHealthHistory(
                    org_id=client.org_id,
                    client_id=client.id,
                    score=result["score"],
                    tier=result["tier"],
                    components=result["components"],
                )
                db.add(history)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(
                    f"Health score failed for client {client.id}: {e}")
        db.commit()
    finally:
        db.close()
