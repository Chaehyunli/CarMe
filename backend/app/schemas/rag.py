from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserVehicleCreate(BaseModel):
    catalog_id: UUID
    nickname: str = Field(min_length=1, max_length=40)


class UserVehicleResponse(BaseModel):
    id: UUID
    catalog_id: UUID
    nickname: str
    display_name: str
    created_at: datetime


class ChatSessionCreate(BaseModel):
    vehicle_id: UUID


class ChatManualResponse(BaseModel):
    id: UUID
    title: str
    manual_type: str
    pdf_page_count: int
    is_primary: bool
    download_available: bool = True


class ChatSessionResponse(BaseModel):
    id: UUID
    vehicle_id: UUID
    expires_at: datetime
    manuals: list[ChatManualResponse]


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    category: str | None = Field(default=None, max_length=50)


class CitationResponse(BaseModel):
    manual_id: UUID | None = None
    manual_title: str
    pdf_page_number: int | None = None
    printed_page_number: str | None = None
    quote_text: str
    source_type: str = "PDF_MANUAL"
    source_url: str | None = None


class ChatMessageResponse(BaseModel):
    result_status: str
    answer: str | None = None
    citations: list[CitationResponse] = Field(default_factory=list)
    clarifying_question: str | None = None
    escalation: str | None = None
    # Used only when a web-only Hyundai manual must be opened by the user;
    # this is intentionally separate from a quoted RAG citation.
    official_manual_url: str | None = None
    official_manual_label: str | None = None
    expires_at: datetime


class DownloadResponse(BaseModel):
    url: str
    filename: str
    expires_at: datetime
