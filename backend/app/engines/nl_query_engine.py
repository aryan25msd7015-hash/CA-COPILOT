"""Guardrailed natural-language to SQL helpers."""
import re
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text

SCHEMA_CONTEXT = """
organizations(id, name, plan, gstin)
clients(id, org_id, name, gstin, health_score, industry)
documents(id, org_id, client_id, doc_type, status, source, created_at)
transactions(id, org_id, client_id, invoice_no, vendor_gstin, vendor_name,
             amount, tax_amount, date, match_status, anomaly_score, fraud_flag)
compliance_deadlines(id, org_id, client_id, filing_type, period, deadline, status)
anomaly_flags(id, org_id, client_id, transaction_id, flag_type, risk_score, reviewed)
reconciliation_results(id, org_id, client_id, period, total_purchase,
                       total_gstr2b, matched_count, unmatched_count, mismatch_value)
"""

STARTER_PROMPTS = [
    {"category": "Client Risk", "intent": "risk_triage", "prompt": "Which clients have a health score below 50?", "recommended": True},
    {"category": "Deadlines", "intent": "upcoming_deadlines", "prompt": "Show pending deadlines due in the next 10 days.", "recommended": True},
    {"category": "Reconciliation", "intent": "unmatched_value", "prompt": "List unmatched purchase transactions by value.", "recommended": True},
    {"category": "Audit", "intent": "anomaly_risk", "prompt": "Which vendors have the highest anomaly scores?", "recommended": True},
    {"category": "Invoices", "intent": "fraud_queue", "prompt": "Show all fraud flagged invoices.", "recommended": True},
    {"category": "Reconciliation", "intent": "client_match_summary", "prompt": "Compare matched and unmatched counts by client.", "recommended": False},
    {"category": "Deadlines", "intent": "overdue_filings", "prompt": "Which clients have overdue filings?", "recommended": False},
    {"category": "Purchases", "intent": "monthly_purchase_value", "prompt": "Show total purchase value by month.", "recommended": False},
    {"category": "Audit", "intent": "duplicate_anomalies", "prompt": "List duplicate transaction anomalies.", "recommended": False},
    {"category": "Documents", "intent": "missing_gstr2b", "prompt": "Which clients have not submitted GSTR-2B documents?", "recommended": False},
]
STARTER_QUERIES = [item["prompt"] for item in STARTER_PROMPTS]

BLOCKED_KEYWORDS = [
    "DELETE", "UPDATE", "INSERT", "DROP", "TRUNCATE", "ALTER", "CREATE",
    "GRANT", "REVOKE", "COPY", "CALL", "DO", "EXECUTE",
]


def translate_to_sql_fallback(question: str) -> str:
    normalized = " ".join(question.lower().split())
    if "health" in normalized and ("below" in normalized or "low" in normalized):
        threshold_match = re.search(r"\b(?:below|under|less than)\s+(\d{1,3})\b", normalized)
        threshold = min(100, max(0, int(threshold_match.group(1)))) if threshold_match else 50
        return (
            "SELECT name, gstin, health_score, industry "
            "FROM clients WHERE org_id = :org_id AND health_score < "
            f"{threshold} ORDER BY health_score ASC, name ASC LIMIT 100"
        )
    if "pending" in normalized and "deadline" in normalized:
        return (
            "SELECT c.name AS client_name, d.filing_name, d.filing_type, d.period, d.deadline, d.status "
            "FROM compliance_deadlines d JOIN clients c ON c.id = d.client_id "
            "WHERE d.org_id = :org_id AND c.org_id = :org_id AND d.status = 'pending' "
            "ORDER BY d.deadline ASC LIMIT 100"
        )
    if "unmatched" in normalized and ("transaction" in normalized or "purchase" in normalized):
        return (
            "SELECT c.name AS client_name, t.invoice_no, t.vendor_name, t.vendor_gstin, t.amount, t.date, t.match_status "
            "FROM transactions t JOIN clients c ON c.id = t.client_id "
            "WHERE t.org_id = :org_id AND c.org_id = :org_id AND t.match_status = 'unmatched' "
            "ORDER BY t.amount DESC NULLS LAST LIMIT 100"
        )
    if "fraud" in normalized and ("invoice" in normalized or "flag" in normalized):
        return (
            "SELECT c.name AS client_name, t.invoice_no, t.vendor_name, t.vendor_gstin, t.amount, t.fraud_flag, t.fraud_review_status "
            "FROM transactions t JOIN clients c ON c.id = t.client_id "
            "WHERE t.org_id = :org_id AND c.org_id = :org_id AND t.fraud_flag IS NOT NULL "
            "ORDER BY t.created_at DESC LIMIT 100"
        )
    if "anomaly" in normalized or "anomalies" in normalized:
        return (
            "SELECT c.name AS client_name, a.flag_type, a.risk_score, a.review_status, a.details, a.created_at "
            "FROM anomaly_flags a JOIN clients c ON c.id = a.client_id "
            "WHERE a.org_id = :org_id AND c.org_id = :org_id "
            "ORDER BY a.risk_score DESC NULLS LAST LIMIT 100"
        )
    if "matched" in normalized and "unmatched" in normalized and "client" in normalized:
        return (
            "SELECT c.name AS client_name, r.period, r.matched_count, r.unmatched_count, r.mismatch_value "
            "FROM reconciliation_results r JOIN clients c ON c.id = r.client_id "
            "WHERE r.org_id = :org_id AND c.org_id = :org_id "
            "ORDER BY r.run_at DESC LIMIT 100"
        )
    if "documents" in normalized or "submitted" in normalized:
        return (
            "SELECT c.name AS client_name, d.doc_type, d.status, d.source, d.created_at "
            "FROM documents d JOIN clients c ON c.id = d.client_id "
            "WHERE d.org_id = :org_id AND c.org_id = :org_id "
            "ORDER BY d.created_at DESC LIMIT 100"
        )
    return (
        "SELECT name, gstin, pan, health_score, industry, status, created_at "
        "FROM clients WHERE org_id = :org_id ORDER BY created_at DESC LIMIT 100"
    )


def translate_to_sql(question: str, org_id: str, anthropic_client) -> str:
    prompt = f"""Translate the question into one PostgreSQL SELECT query.
Use only the schema below. Every tenant-owned table must be filtered using
org_id = :org_id. Return SQL only, without markdown.

SCHEMA:
{SCHEMA_CONTEXT}

QUESTION:
{question}
"""
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        system="You produce read-only, parameterized PostgreSQL queries.",
        messages=[{"role": "user", "content": prompt}],
    )
    sql = response.content[0].text.strip()
    sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql, flags=re.IGNORECASE)
    validate_sql(sql)
    return sql


def validate_sql(sql: str) -> None:
    normalized = re.sub(r"--.*?$|/\*.*?\*/", " ", sql, flags=re.MULTILINE | re.DOTALL).strip()
    upper = normalized.upper()
    if not (upper.startswith("SELECT ") or upper.startswith("WITH ")):
        raise ValueError("Only SELECT queries are allowed")
    if ";" in normalized.rstrip(";"):
        raise ValueError("Only one SQL statement is allowed")
    for keyword in BLOCKED_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper):
            raise ValueError(f"Blocked SQL keyword: {keyword}")
    if ":org_id" not in normalized:
        raise ValueError("Query must include the :org_id tenant parameter")
    if re.search(r"\b(pg_|information_schema|current_setting|set_config)\b", upper, re.IGNORECASE):
        raise ValueError("System catalog access is not allowed")


def execute_query(sql: str, org_id: str, db) -> dict:
    validate_sql(sql)
    result = db.execute(text(sql), {"org_id": org_id})
    def serializable(value):
        if isinstance(value, (date, datetime, UUID)):
            return str(value)
        if isinstance(value, Decimal):
            return float(value)
        return value

    rows = [{key: serializable(value) for key, value in row._mapping.items()}
            for row in result.fetchmany(500)]
    return {"sql": sql, "rows": rows, "row_count": len(rows)}
