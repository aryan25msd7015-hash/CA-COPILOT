import pandas as pd
from sklearn.ensemble import IsolationForest

from app.engines.anomaly_detector import score_transaction, train_isolation_forest


def test_trains_real_isolation_forest():
    frame = pd.DataFrame([
        {"vendor_gstin": f"GSTIN{i}", "amount": amount}
        for i, amount in enumerate([100, 105, 110, 115, 120, 10000])
    ])
    model, stats = train_isolation_forest(frame)

    assert isinstance(model, IsolationForest)
    assert not stats.empty


def test_unknown_vendor_has_elevated_risk():
    frame = pd.DataFrame([
        {"vendor_gstin": f"GSTIN{i}", "amount": amount}
        for i, amount in enumerate([100, 105, 110, 115])
    ])
    model, stats = train_isolation_forest(frame)

    assert score_transaction(model, stats, "UNKNOWN", 100) == 0.75
