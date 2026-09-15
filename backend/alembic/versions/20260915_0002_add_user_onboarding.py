"""Add first-login role onboarding state.

Revision ID: 20260915_0002
Revises: 20260915_0001
Create Date: 2026-09-15
"""

import sqlalchemy as sa

from alembic import op

revision = "20260915_0002"
down_revision = "20260915_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed")
