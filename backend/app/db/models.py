import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class CatalogStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ManualStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    UPLOADED = "UPLOADED"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    kakao_subject: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        sa.Enum(UserRole, name="user_role"), nullable=False, server_default=UserRole.USER.value
    )
    status: Mapped[UserStatus] = mapped_column(
        sa.Enum(UserStatus, name="user_status"), nullable=False, server_default=UserStatus.ACTIVE.value
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class VehicleCatalog(Base):
    __tablename__ = "vehicle_catalogs"
    __table_args__ = (
        sa.UniqueConstraint("manufacturer", "model_name", "model_year", name="uq_vehicle_catalog_model"),
        sa.Index("ix_vehicle_catalog_status_model", "status", "manufacturer", "model_name", "model_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    manufacturer: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    model_year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(220), nullable=False)
    status: Mapped[CatalogStatus] = mapped_column(
        sa.Enum(CatalogStatus, name="catalog_status"),
        nullable=False,
        server_default=CatalogStatus.DRAFT.value,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
    )


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        sa.Index(
            "uq_vehicle_active_user_catalog",
            "user_id",
            "catalog_id",
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True
    )
    catalog_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vehicle_catalogs.id"), nullable=False
    )
    nickname: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Manual(Base):
    __tablename__ = "manuals"
    __table_args__ = (sa.Index("ix_manual_status_type_locale", "status", "manual_type", "locale"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    manual_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    locale: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    source_url: Mapped[str | None] = mapped_column(sa.String(2048))
    object_key: Mapped[str] = mapped_column(sa.String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    pdf_page_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[ManualStatus] = mapped_column(
        sa.Enum(ManualStatus, name="manual_status"),
        nullable=False,
        server_default=ManualStatus.DRAFT.value,
    )
    ingestion_error: Mapped[str | None] = mapped_column(sa.Text)
    embedding_model_version: Mapped[str | None] = mapped_column(sa.String(255))
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    indexed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class ManualApplicability(Base):
    __tablename__ = "manual_applicabilities"
    __table_args__ = (
        sa.Index(
            "uq_manual_applicability_primary_catalog",
            "catalog_id",
            unique=True,
            postgresql_where=sa.text("is_primary IS TRUE"),
        ),
    )

    manual_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("manuals.id"), primary_key=True
    )
    catalog_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vehicle_catalogs.id"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")


class ManualSection(Base):
    __tablename__ = "manual_sections"
    __table_args__ = (
        sa.UniqueConstraint("manual_id", "toc_order", name="uq_manual_section_toc_order"),
        sa.CheckConstraint("pdf_page_start <= pdf_page_end", name="ck_manual_section_page_range"),
        sa.Index("ix_manual_section_page_range", "manual_id", "pdf_page_start", "pdf_page_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    manual_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("manuals.id"), nullable=False
    )
    parent_section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("manual_sections.id")
    )
    title: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    toc_order: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    pdf_page_start: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    pdf_page_end: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    retrieval_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    embedding_model_version: Mapped[str | None] = mapped_column(sa.String(255))


class ManualChunk(Base):
    __tablename__ = "manual_chunks"
    __table_args__ = (
        sa.Index(
            "ix_manual_chunk_location",
            "manual_id",
            "section_id",
            "pdf_page_number",
            "chunk_order",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    manual_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("manuals.id"), nullable=False
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("manual_sections.id"), nullable=False
    )
    chunk_order: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    pdf_page_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    printed_page_number: Mapped[str | None] = mapped_column(sa.String(50))
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    embedding_model_version: Mapped[str | None] = mapped_column(sa.String(255))
