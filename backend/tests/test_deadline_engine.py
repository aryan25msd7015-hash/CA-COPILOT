from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.engines.deadline_engine import compute_days_before_alert


def _db_with_history(history):
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = history
    return db


def test_new_client_uses_default_alert_window():
    assert compute_days_before_alert("client", "GSTR1", _db_with_history([])) == 7


def test_chronic_late_filer_gets_earlier_alert():
    due = date(2026, 1, 1)
    history = [
        SimpleNamespace(status="filed", deadline=due, filed_at=datetime.combine(due + timedelta(days=7), datetime.min.time()))
        for _ in range(3)
    ]
    assert compute_days_before_alert("client", "GSTR1", _db_with_history(history)) == 12
