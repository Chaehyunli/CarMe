"""Resumable local PDF extraction and Ollama embedding jobs."""

import re
from collections.abc import Callable
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
from app.db.session import SessionLocal
from app.services.embeddings import embed_texts
from app.services.storage import PrivateStorage


def _clean_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def _chunks(text: str, limit: int = 1200, overlap: int = 180) -> list[str]:
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
        if part := text[start:end].strip():
            parts.append(part)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return parts


def prepare_manual_for_indexing(db: Session, manual: Manual, *, force: bool = False) -> tuple[int, int]:
    """Persist PDF chunks first; embedding runs separately and can take minutes."""
    allowed = {ManualStatus.UPLOADED, ManualStatus.FAILED}
    if force:
        allowed.add(ManualStatus.READY)
    if manual.status not in allowed:
        raise ValueError("업로드 검증이 끝난 매뉴얼만 문서 테스트 준비를 할 수 있습니다.")
    manual.status = ManualStatus.INDEXING
    manual.ingestion_error = None
    manual.indexing_total_chunks = 0
    manual.embedded_chunk_count = 0
    db.commit()
    pdf = None
    try:
        pdf = open_pdf(stream=PrivateStorage(get_settings()).read_bytes(manual.object_key), filetype="pdf")
        db.query(ManualChunk).filter(ManualChunk.manual_id == manual.id).delete(synchronize_session=False)
        db.query(ManualSection).filter(ManualSection.manual_id == manual.id).delete(synchronize_session=False)
        pages: list[tuple[int, UUID, str]] = []
        for number, page in enumerate(pdf, start=1):
            text = _clean_text(page.get_text("text"))
            if len(text) < 25:
                continue
            section_id = uuid4()
            db.add(ManualSection(id=section_id, manual_id=manual.id, parent_section_id=None, title=f"PDF {number}쪽", toc_order=number, pdf_page_start=number, pdf_page_end=number, retrieval_text=text[:3000], embedding=None, embedding_model_version=None))
            pages.append((number, section_id, text))
        if not pages:
            raise ValueError("PDF에서 검색 가능한 텍스트를 추출하지 못했습니다.")
        db.flush()
        order = 0
        for number, section_id, text in pages:
            for content in _chunks(text):
                order += 1
                db.add(ManualChunk(id=uuid4(), manual_id=manual.id, section_id=section_id, chunk_order=order, pdf_page_number=number, printed_page_number=None, content=content, embedding=None, embedding_model_version=None))
        manual.indexing_total_chunks = order
        db.commit()
        return len(pages), order
    except Exception as exc:
        db.rollback()
        failed = db.get(Manual, manual.id)
        if failed is not None:
            failed.status = ManualStatus.FAILED
            failed.ingestion_error = str(exc)[:2000]
            db.commit()
        raise
    finally:
        if pdf is not None:
            pdf.close()


def embed_manual_in_background(
    manual_id: UUID,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> None:
    """One committed batch at a time: safe across long local-model runs."""
    settings = get_settings()
    with SessionLocal() as db:
        manual = db.get(Manual, manual_id)
        if manual is None or manual.status != ManualStatus.INDEXING:
            return
        if progress_callback is not None:
            progress_callback(manual.title, manual.embedded_chunk_count, manual.indexing_total_chunks)
        try:
            while True:
                batch = list(db.scalars(select(ManualChunk).where(ManualChunk.manual_id == manual.id, ManualChunk.embedding.is_(None)).order_by(ManualChunk.chunk_order).limit(settings.embedding_batch_size)))
                if not batch:
                    manual.status = ManualStatus.READY
                    manual.indexed_at = datetime.now(UTC)
                    manual.embedding_model_version = settings.ollama_embedding_model
                    for catalog in db.scalars(select(VehicleCatalog).join(ManualApplicability, ManualApplicability.catalog_id == VehicleCatalog.id).where(ManualApplicability.manual_id == manual.id, ManualApplicability.is_primary.is_(True))):
                        if catalog.status != CatalogStatus.ARCHIVED:
                            catalog.status = CatalogStatus.ACTIVE
                    db.commit()
                    if progress_callback is not None:
                        progress_callback(manual.title, manual.embedded_chunk_count, manual.indexing_total_chunks)
                    return
                vectors = embed_texts([chunk.content for chunk in batch], settings)
                for chunk, vector in zip(batch, vectors, strict=True):
                    chunk.embedding = vector
                    chunk.embedding_model_version = settings.ollama_embedding_model
                manual.embedded_chunk_count += len(batch)
                db.commit()
                if progress_callback is not None:
                    progress_callback(manual.title, manual.embedded_chunk_count, manual.indexing_total_chunks)
        except Exception as exc:  # noqa: BLE001 - persist any background-job failure for the admin
            db.rollback()
            failed = db.get(Manual, manual_id)
            if failed is not None:
                failed.status = ManualStatus.FAILED
                failed.ingestion_error = str(exc)[:2000]
                db.commit()


def index_manual_for_local_test(db: Session, manual: Manual, *, force: bool = False) -> int:
    """Synchronous compatibility helper for scripts; UI uses the background job."""
    pages, _ = prepare_manual_for_indexing(db, manual, force=force)
    embed_manual_in_background(manual.id)
    db.refresh(manual)
    if manual.status != ManualStatus.READY:
        raise RuntimeError(manual.ingestion_error or "임베딩 생성에 실패했습니다.")
    return pages
