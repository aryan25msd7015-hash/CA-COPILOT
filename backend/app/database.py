"""
SQLAlchemy engine, session factory, declarative base, and get_db() dependency.
Uses a synchronous psycopg2 driver as required by the design document.
"""
from contextvars import ContextVar, Token

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from .config import settings


# ── Engine (sync, psycopg2) ────────────────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,          # detect stale connections
    pool_size=10,
    max_overflow=20,
    echo=settings.SQL_ECHO,
)

# ── Session factory ────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

current_org_id: ContextVar[str | None] = ContextVar("current_org_id", default=None)


def set_current_org(org_id: str | None) -> Token:
    return current_org_id.set(org_id)


def reset_current_org(token: Token) -> None:
    current_org_id.reset(token)


@event.listens_for(Session, "after_begin")
def apply_tenant_context(session, transaction, connection):
    """Set the PostgreSQL RLS tenant variable for the current transaction."""
    org_id = current_org_id.get()
    if org_id and connection.dialect.name == "postgresql":
        connection.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(org_id)},
        )


# ── Declarative base ───────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── FastAPI dependency ─────────────────────────────────────────────────────
def get_db():
    """Yield a database session and guarantee it is closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
