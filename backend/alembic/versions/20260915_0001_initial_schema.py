"""Create CarMe persistent schema.

Revision ID: 20260915_0001
Revises:
Create Date: 2026-09-15
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260915_0001"
down_revision = None
branch_labels = None
depends_on = None


user_role = postgresql.ENUM("USER", "ADMIN", name="user_role", create_type=False)
user_status = postgresql.ENUM("ACTIVE", "SUSPENDED", "DELETED", name="user_status", create_type=False)
catalog_status = postgresql.ENUM("DRAFT", "ACTIVE", "ARCHIVED", name="catalog_status", create_type=False)
manual_status = postgresql.ENUM(
    "DRAFT", "UPLOADED", "INDEXING", "READY", "FAILED", "ARCHIVED", name="manual_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for enum_type in (user_role, user_status, catalog_status, manual_status):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kakao_subject", sa.String(length=255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="USER"),
        sa.Column("status", user_status, nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_table(
        "vehicle_catalogs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("manufacturer", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("model_year", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=220), nullable=False),
        sa.Column("status", catalog_status, nullable=False, server_default="DRAFT"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("manufacturer", "model_name", "model_year", name="uq_vehicle_catalog_model"),
    )
    op.create_index(
        "ix_vehicle_catalog_status_model",
        "vehicle_catalogs",
        ["status", "manufacturer", "model_name", "model_year"],
    )
    op.create_table(
        "vehicles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("catalog_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicle_catalogs.id"), nullable=False),
        sa.Column("nickname", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_vehicles_user_id", "vehicles", ["user_id"])
    op.create_index(
        "uq_vehicle_active_user_catalog",
        "vehicles",
        ["user_id", "catalog_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "manuals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("manual_type", sa.String(length=100), nullable=False),
        sa.Column("locale", sa.String(length=20), nullable=False),
        sa.Column("source_url", sa.String(length=2048)),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False, unique=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("pdf_page_count", sa.Integer(), nullable=False),
        sa.Column("status", manual_status, nullable=False, server_default="DRAFT"),
        sa.Column("ingestion_error", sa.Text()),
        sa.Column("embedding_model_version", sa.String(length=255)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True)),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_manual_status_type_locale", "manuals", ["status", "manual_type", "locale"])
    op.create_table(
        "manual_applicabilities",
        sa.Column("manual_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manuals.id"), primary_key=True),
        sa.Column("catalog_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicle_catalogs.id"), primary_key=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "uq_manual_applicability_primary_catalog",
        "manual_applicabilities",
        ["catalog_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )
    op.create_table(
        "manual_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("manual_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manuals.id"), nullable=False),
        sa.Column("parent_section_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manual_sections.id")),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("toc_order", sa.Integer(), nullable=False),
        sa.Column("pdf_page_start", sa.Integer(), nullable=False),
        sa.Column("pdf_page_end", sa.Integer(), nullable=False),
        sa.Column("retrieval_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024)),
        sa.Column("embedding_model_version", sa.String(length=255)),
        sa.UniqueConstraint("manual_id", "toc_order", name="uq_manual_section_toc_order"),
        sa.CheckConstraint("pdf_page_start <= pdf_page_end", name="ck_manual_section_page_range"),
    )
    op.create_index(
        "ix_manual_section_page_range",
        "manual_sections",
        ["manual_id", "pdf_page_start", "pdf_page_end"],
    )
    op.create_table(
        "manual_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("manual_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manuals.id"), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manual_sections.id"), nullable=False),
        sa.Column("chunk_order", sa.Integer(), nullable=False),
        sa.Column("pdf_page_number", sa.Integer(), nullable=False),
        sa.Column("printed_page_number", sa.String(length=50)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024)),
        sa.Column("embedding_model_version", sa.String(length=255)),
    )
    op.create_index(
        "ix_manual_chunk_location",
        "manual_chunks",
        ["manual_id", "section_id", "pdf_page_number", "chunk_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_manual_chunk_location", table_name="manual_chunks")
    op.drop_table("manual_chunks")
    op.drop_index("ix_manual_section_page_range", table_name="manual_sections")
    op.drop_table("manual_sections")
    op.drop_index("uq_manual_applicability_primary_catalog", table_name="manual_applicabilities")
    op.drop_table("manual_applicabilities")
    op.drop_index("ix_manual_status_type_locale", table_name="manuals")
    op.drop_table("manuals")
    op.drop_index("uq_vehicle_active_user_catalog", table_name="vehicles")
    op.drop_index("ix_vehicles_user_id", table_name="vehicles")
    op.drop_table("vehicles")
    op.drop_index("ix_vehicle_catalog_status_model", table_name="vehicle_catalogs")
    op.drop_table("vehicle_catalogs")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_type in (manual_status, catalog_status, user_status, user_role):
        enum_type.drop(bind, checkfirst=True)
