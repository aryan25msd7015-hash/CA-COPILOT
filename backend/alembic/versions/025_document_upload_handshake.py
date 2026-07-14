"""Document upload handshake metadata.

Revision ID: 025
Revises: 024
Create Date: 2026-06-23 01:25:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_status",
        "documents",
        "status IN ('pending_upload','received','pending','ocr_complete','ocr_failed','parse_failed','processed')",
    )
    op.add_column("documents", sa.Column("original_filename", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("file_size_bytes", sa.String(length=30), nullable=True))
    op.add_column("documents", sa.Column("mime_type", sa.String(length=100), nullable=True))
    op.add_column("documents", sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("documents", sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_documents_uploaded_by_user", "documents", "users", ["uploaded_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_documents_uploaded_by_user_id"), "documents", ["uploaded_by_user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_documents_uploaded_by_user_id"), table_name="documents")
    op.drop_constraint("fk_documents_uploaded_by_user", "documents", type_="foreignkey")
    op.drop_column("documents", "received_at")
    op.drop_column("documents", "upload_expires_at")
    op.drop_column("documents", "uploaded_by_user_id")
    op.drop_column("documents", "mime_type")
    op.drop_column("documents", "file_size_bytes")
    op.drop_column("documents", "original_filename")
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_status",
        "documents",
        "status IN ('pending','ocr_complete','ocr_failed','parse_failed','processed')",
    )
