"""Add admin-verified Hyundai web manual links to vehicle catalogs.

Revision ID: 20260915_0004
Revises: 20260915_0003
Create Date: 2026-09-15
"""

import sqlalchemy as sa

from alembic import op

revision = "20260915_0004"
down_revision = "20260915_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicle_catalogs", sa.Column("official_manual_url", sa.String(length=2048)))


def downgrade() -> None:
    op.drop_column("vehicle_catalogs", "official_manual_url")
