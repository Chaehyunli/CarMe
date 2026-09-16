"""Align pgvector columns with qwen3-embedding:4b output dimensions.

Revision ID: 20260915_0005
Revises: 20260915_0004
Create Date: 2026-09-15
"""

from alembic import op

revision = "20260915_0005"
down_revision = "20260915_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing local MVP rows were deliberately NULL, so this is a safe type
    # alignment before the first real embedding rebuild.
    op.execute("ALTER TABLE manual_sections ALTER COLUMN embedding TYPE vector(2560) USING embedding::vector(2560)")
    op.execute("ALTER TABLE manual_chunks ALTER COLUMN embedding TYPE vector(2560) USING embedding::vector(2560)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_manual_chunks_embedding_hnsw "
        "ON manual_chunks USING hnsw ((embedding::halfvec(2560)) halfvec_cosine_ops) "
        "WITH (m = 16, ef_construction = 64) WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_manual_chunks_embedding_hnsw")
    op.execute("ALTER TABLE manual_chunks ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector(1024)")
    op.execute("ALTER TABLE manual_sections ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector(1024)")
