"""Small helper for recording auditable platform activity."""
from app.models.extensions import UserActivityLog


def log_activity(db, org_id, user_id, activity_type, client_id=None, duration_seconds=300, details=None):
    db.add(UserActivityLog(
        org_id=org_id, user_id=user_id, client_id=client_id,
        activity_type=activity_type, duration_seconds=duration_seconds,
        details=details or {},
    ))
