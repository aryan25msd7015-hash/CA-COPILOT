"""Optional production observability integrations."""
from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

REQUEST_COUNTER = None
REQUEST_LATENCY = None
ERROR_COUNTER = None


def configure_observability() -> dict[str, Any]:
    status = {
        "sentry_configured": bool(settings.SENTRY_DSN),
        "metrics_enabled": bool(settings.METRICS_ENABLED),
        "prometheus_available": False,
    }
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                environment=settings.ENV,
                traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
                send_default_pii=False,
            )
        except Exception as exc:
            logger.warning("Sentry init failed: %s", exc)
            status["sentry_error"] = str(exc)
    if settings.METRICS_ENABLED:
        _init_prometheus(status)
    return status


def observability_status() -> dict[str, Any]:
    return {
        "sentry_configured": bool(settings.SENTRY_DSN),
        "metrics_enabled": bool(settings.METRICS_ENABLED),
        "metrics_protected": bool(settings.METRICS_BEARER_TOKEN),
        "traces_sample_rate": settings.SENTRY_TRACES_SAMPLE_RATE,
    }


def record_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    if REQUEST_COUNTER is not None:
        REQUEST_COUNTER.labels(method=method, path=path, status=str(status_code)).inc()
    if REQUEST_LATENCY is not None:
        REQUEST_LATENCY.labels(method=method, path=path).observe(duration_seconds)
    if ERROR_COUNTER is not None and status_code >= 500:
        ERROR_COUNTER.labels(method=method, path=path, status=str(status_code)).inc()


def render_metrics() -> tuple[bytes, str]:
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return generate_latest(), CONTENT_TYPE_LATEST
    except Exception as exc:
        raise RuntimeError(f"Prometheus metrics unavailable: {exc}") from exc


def _init_prometheus(status: dict[str, Any]) -> None:
    global REQUEST_COUNTER, REQUEST_LATENCY, ERROR_COUNTER
    try:
        from prometheus_client import Counter, Histogram

        REQUEST_COUNTER = Counter(
            "ca_copilot_http_requests_total",
            "Total HTTP requests",
            ["method", "path", "status"],
        )
        REQUEST_LATENCY = Histogram(
            "ca_copilot_http_request_duration_seconds",
            "HTTP request latency",
            ["method", "path"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
        )
        ERROR_COUNTER = Counter(
            "ca_copilot_http_errors_total",
            "HTTP 5xx responses",
            ["method", "path", "status"],
        )
        status["prometheus_available"] = True
    except ValueError:
        # Test clients can import the app repeatedly in one Python process.
        status["prometheus_available"] = True
    except Exception as exc:
        logger.warning("Prometheus init failed: %s", exc)
        status["prometheus_error"] = str(exc)
