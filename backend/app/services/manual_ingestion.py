"""Small, synchronous PDF ingestion path used by the local RAG test MVP."""

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fitz import open as open_pdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    CatalogStatus,
    Manual,
    ManualApplicability,
    ManualChunk,
    ManualSection,
    ManualStatus,
    VehicleCatalog,
)
from app.services.storage import PrivateStorage


def _clean_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def _chunks(text: str, limit: int = 1200, overlap: int = 180) -> list[str]:
    """Keep chunks within one PDF page and prefer a paragraph boundary."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start + limit // 2, end), text.rfind(". ", start + limit // 2, end))
            if boundary > start:
                end = boundary + 1
        part = text[start:end].strip()
        if part:
            parts.append(part)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return parts


def index_manual_for_local_test(db: Session, manual: Manual) -> int:
    """Extract page text and make one local-test manual searchable.

    This deliberately stores no embeddings yet: it makes the uploaded PDF testable
    immediately with deterministic lexical retrieval and Qwen grounded generation.
    """
    if manual.status not in {ManualStatus.UPLOADED, ManualStatus.FAILED}:
        raise ValueError("업로드 검증이 끝난 매뉴얼만 문서 테스트 준비를 할 수 있습니다.")

    manual.status = ManualStatus.INDEXING
    manual.ingestion_error = None
    db.commit()
    try:
        pdf = open_pdf(stream=PrivateStorage(get_settings()).read_bytes(manual.object_key), filetype="pdf")
        db.query(ManualChunk).filter(ManualChunk.manual_id == manual.id).delete(synchronize_session=False)
        db.query(ManualSection).filter(ManualSection.manual_id == manual.id).delete(synchronize_session=False)

        indexed_pages = 0
        page_sections: list[tuple[int, UUID, str]] = []
        for page_index, page in enumerate(pdf, start=1):
            page_text = _clean_text(page.get_text("text"))
            if len(page_text) < 25:
                continue
            section_id = uuid4()
            db.add(
                ManualSection(
                    id=section_id,
                    manual_id=manual.id,
                    parent_section_id=None,
                    title=f"PDF {page_index}쪽",
                    toc_order=page_index,
                    pdf_page_start=page_index,
                    pdf_page_end=page_index,
                    retrieval_text=page_text[:3000],
                    embedding=None,
                    embedding_model_version=None,
                )
            )
            page_sections.append((page_index, section_id, page_text))
            indexed_pages += 1

        # Flush parent rows before adding chunks. SQLAlchemy cannot infer this
        # dependency because the IDs are assigned directly rather than through
        # ORM relationship attributes.
        db.flush()
        chunk_order = 0
        for page_index, section_id, page_text in page_sections:
            for piece in _chunks(page_text):
                chunk_order += 1
                db.add(
                    ManualChunk(
                        id=uuid4(),
                        manual_id=manual.id,
                        section_id=section_id,
                        chunk_order=chunk_order,
                        pdf_page_number=page_index,
                        printed_page_number=None,
                        content=piece,
                        embedding=None,
                        embedding_model_version=None,
                    )
                )
        pdf.close()
        if not indexed_pages:
            raise ValueError("PDF에서 검색 가능한 텍스트를 추출하지 못했습니다.")

        manual.status = ManualStatus.READY
        manual.indexed_at = datetime.now(UTC)
        manual.embedding_model_version = "lexical-rag-test-v1"
        for catalog in db.scalars(
            select(VehicleCatalog)
            .join(ManualApplicability, ManualApplicability.catalog_id == VehicleCatalog.id)
            .where(ManualApplicability.manual_id == manual.id, ManualApplicability.is_primary.is_(True))
        ):
            if catalog.status != CatalogStatus.ARCHIVED:
                catalog.status = CatalogStatus.ACTIVE
        db.commit()
        return indexed_pages
    except Exception as exc:
        db.rollback()
        manual = db.get(Manual, manual.id)
        if manual is not None:
            manual.status = ManualStatus.FAILED
            manual.ingestion_error = str(exc)[:2000]
            db.commit()
        raise
