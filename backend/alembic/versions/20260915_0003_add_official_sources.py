"""Add cached Hyundai official web-manual sources.

Revision ID: 20260915_0003
Revises: 20260915_0002
Create Date: 2026-09-15
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260915_0003"
down_revision = "20260915_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "official_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("catalog_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicle_catalogs.id"), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("system_variant", sa.String(length=100)),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="READY"),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_error", sa.Text()),
        sa.UniqueConstraint("catalog_id", "source_url", name="uq_official_source_catalog_url"),
    )
    op.create_index(
        "ix_official_source_catalog_type",
        "official_sources",
        ["catalog_id", "source_type", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_official_source_catalog_type", table_name="official_sources")
    op.drop_table("official_sources")
