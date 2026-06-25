from sqlalchemy.orm import Session
from fastapi import HTTPException, status


def scoped(db: Session, Model, org_id: str):
    """Return a query filtered by org_id. Raises RuntimeError if Model lacks org_id."""
    if not hasattr(Model, 'org_id'):
        raise RuntimeError(f"{Model.__name__} does not have an org_id column — use a direct query instead.")
    return db.query(Model).filter(Model.org_id == org_id)
