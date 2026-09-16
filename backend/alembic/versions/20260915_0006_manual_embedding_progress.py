"""Persist per-manual embedding progress for asynchronous indexing.

Revision ID: 20260915_0006
Revises: 20260915_0005
Create Date: 2026-09-15
"""

import sqlalchemy as sa

from alembic import op

revision = "20260915_0006"
down_revision = "20260915_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manuals", sa.Column("indexing_total_chunks", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("manuals", sa.Column("embedded_chunk_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("manuals", "embedded_chunk_count")
    op.drop_column("manuals", "indexing_total_chunks")
