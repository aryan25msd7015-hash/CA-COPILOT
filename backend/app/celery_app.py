"""
Celery application instance with Redis broker/backend and four dedicated queues.
Queue routing:
  ocr       — Azure OCR tasks
  heavy     — reconciliation, anomaly detection, health scores
  llm       — RAG drafter, NL query, audit papers
  whatsapp  — outbound/inbound WhatsApp message handling
"""
from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery("ca_platform")

celery_app.conf.update(
    # ── Broker & result backend ────────────────────────────────────────
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    broker_connection_retry_on_startup=True,

    # ── Serialisation ──────────────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # ── Timezone ───────────────────────────────────────────────────────
    timezone="Asia/Kolkata",
    enable_utc=True,

    # ── Queue routing ──────────────────────────────────────────────────
    task_routes={
        "app.tasks.ocr_tasks.*":              {"queue": "ocr"},
        "app.tasks.reconciliation_tasks.*":   {"queue": "heavy"},
        "app.tasks.anomaly_tasks.*":          {"queue": "heavy"},
        "app.tasks.llm_tasks.*":              {"queue": "llm"},
        "app.tasks.whatsapp_tasks.*":         {"queue": "whatsapp"},
        "app.tasks.health_tasks.*":           {"queue": "heavy"},
        "app.tasks.extension_tasks.process_udyam_certificate": {"queue": "ocr"},
        "app.tasks.extension_tasks.score_deadline_risks": {"queue": "heavy"},
        "app.tasks.autopilot_tasks.refresh_all_autopilot_inboxes": {"queue": "heavy"},
    },

    # ── Task autodiscovery ─────────────────────────────────────────────
    # Import task modules so Celery can discover them at worker startup.
    imports=[
        "app.tasks.ocr_tasks",
        "app.tasks.reconciliation_tasks",
        "app.tasks.anomaly_tasks",
        "app.tasks.llm_tasks",
        "app.tasks.whatsapp_tasks",
        "app.tasks.health_tasks",
        "app.tasks.extension_tasks",
        "app.tasks.autopilot_tasks",
    ],

    # Scheduled maintenance and reminder tasks
    beat_schedule={
        "morning_reminder_check": {
            "task": "app.tasks.whatsapp_tasks.morning_reminder_check",
            "schedule": crontab(hour=9, minute=0),
        },
        "recompute_all_health_scores": {
            "task": "app.tasks.health_tasks.recompute_all_health_scores",
            "schedule": crontab(hour=2, minute=0),
        },
        "score_deadline_risks": {
            "task": "app.tasks.extension_tasks.score_deadline_risks",
            "schedule": crontab(hour=20, minute=0),
        },
        "refresh_all_autopilot_inboxes": {
            "task": "app.tasks.autopilot_tasks.refresh_all_autopilot_inboxes",
            "schedule": crontab(hour=7, minute=30),
        },
    },
)
