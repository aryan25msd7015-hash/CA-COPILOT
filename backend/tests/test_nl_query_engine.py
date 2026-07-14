import pytest

from app.engines.nl_query_engine import validate_sql


def test_allows_tenant_scoped_select():
    validate_sql("SELECT name FROM clients WHERE org_id = :org_id")


@pytest.mark.parametrize("sql", [
    "DELETE FROM clients WHERE org_id = :org_id",
    "SELECT * FROM clients",
    "SELECT * FROM clients WHERE org_id = :org_id; DROP TABLE clients",
])
def test_rejects_unsafe_sql(sql):
    with pytest.raises(ValueError):
        validate_sql(sql)
