PLAN_LIMITS = {
    "starter": {
        "clients": 25,
        "users": 5,
        "documents_per_month": 500,
        "ai_queries_per_month": 250,
        "storage_gb": 10,
    },
    "pro": {
        "clients": 150,
        "users": 25,
        "documents_per_month": 5000,
        "ai_queries_per_month": 2500,
        "storage_gb": 100,
    },
    "premium": {
        "clients": None,
        "users": None,
        "documents_per_month": None,
        "ai_queries_per_month": None,
        "storage_gb": 1000,
    },
}


def plan_limits(plan: str) -> dict:
    return PLAN_LIMITS.get((plan or "starter").lower(), PLAN_LIMITS["starter"])


def usage_status(used: int | float, limit: int | float | None) -> str:
    if limit is None:
        return "unlimited"
    if used >= limit:
        return "exceeded"
    if used >= limit * 0.8:
        return "near_limit"
    return "ok"
