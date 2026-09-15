from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from app.db.models import CatalogStatus, ManualStatus


class AdminVehicleCatalogCreate(BaseModel):
    manufacturer: str = Field(default="HYUNDAI", min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=100)
    model_year: int = Field(ge=1980, le=2100)


class AdminVehicleCatalogUpdate(BaseModel):
    manufacturer: str = Field(default="HYUNDAI", min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=100)
    model_year: int = Field(ge=1980, le=2100)


class AdminVehicleCatalogResponse(BaseModel):
    id: UUID
    manufacturer: str
    model_name: str
    model_year: int
    display_name: str
    status: CatalogStatus
    ready_manual_count: int = 0
    created_at: datetime


class ManualCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    manual_type: str = Field(default="OWNER_MANUAL", min_length=1, max_length=100)
    locale: str = Field(default="ko-KR", min_length=2, max_length=20)
    source_url: HttpUrl | None = None
    catalog_ids: list[UUID] = Field(min_length=1)
    primary_catalog_ids: list[UUID] = Field(default_factory=list)
    original_filename: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    file_size_bytes: int = Field(gt=0, le=200 * 1024 * 1024)


class ManualUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    manual_type: str = Field(min_length=1, max_length=100)
    locale: str = Field(min_length=2, max_length=20)
    catalog_ids: list[UUID] = Field(min_length=1)
    primary_catalog_ids: list[UUID] = Field(default_factory=list)


class ManualResponse(BaseModel):
    id: UUID
    title: str
    manual_type: str
    locale: str
    status: ManualStatus
    original_filename: str
    file_size_bytes: int
    pdf_page_count: int
    catalog_ids: list[UUID]
    primary_catalog_ids: list[UUID]
    applicable_catalogs: list[str]
    created_at: datetime | None = None
    uploaded_at: datetime | None = None
    ingestion_error: str | None = None


class UploadUrlResponse(BaseModel):
    upload_url: str
    expires_in: int
    required_headers: dict[str, str]


class UploadCompleteResponse(BaseModel):
    id: UUID
    status: ManualStatus
    pdf_page_count: int


class ManualIndexResponse(BaseModel):
    id: UUID
    status: ManualStatus
    indexed_page_count: int


class OfficialSourceResponse(BaseModel):
    id: UUID
    source_type: str
    system_variant: str | None = None
    title: str
    source_url: str
    status: str
    synced_at: datetime


class OfficialSourceSyncResponse(BaseModel):
    catalog_id: UUID
    synced_count: int
    sources: list[OfficialSourceResponse]
