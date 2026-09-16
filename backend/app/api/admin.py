# ruff: noqa: B008
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from botocore.exceptions import ClientError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.core.config import get_settings
from app.db.models import (
    CatalogStatus,
    Manual,
    ManualApplicability,
    ManualStatus,
    User,
    VehicleCatalog,
)
from app.db.session import get_db
from app.schemas.admin import (
    AdminVehicleCatalogCreate,
    AdminVehicleCatalogResponse,
    AdminVehicleCatalogUpdate,
    ManualCreateRequest,
    ManualIndexResponse,
    ManualResponse,
    ManualUpdateRequest,
    OfficialManualUrlUpdate,
    OfficialSourceResponse,
    OfficialSourceSyncResponse,
    UploadCompleteResponse,
    UploadUrlResponse,
)
from app.services.manual_ingestion import embed_manual_in_background, prepare_manual_for_indexing
from app.services.official_source_sync import (
    OfficialSourceSyncError,
    resolve_official_sources,
    sync_official_sources,
)
from app.services.storage import PrivateStorage

router = APIRouter(prefix="/admin", tags=["admin"])


def catalog_response(catalog: VehicleCatalog, ready_manual_count: int = 0) -> AdminVehicleCatalogResponse:
    return AdminVehicleCatalogResponse(
        id=catalog.id,
        manufacturer=catalog.manufacturer,
        model_name=catalog.model_name,
        model_year=catalog.model_year,
        display_name=catalog.display_name,
        official_manual_url=catalog.official_manual_url,
        status=catalog.status,
        ready_manual_count=ready_manual_count,
        created_at=catalog.created_at,
    )


@router.get("/vehicle-catalog", response_model=list[AdminVehicleCatalogResponse])
def list_admin_catalogs(
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[AdminVehicleCatalogResponse]:
    ready_count = func.count(Manual.id).filter(Manual.status == ManualStatus.READY)
    rows = db.execute(
        select(VehicleCatalog, ready_count.label("ready_manual_count"))
        .outerjoin(ManualApplicability, ManualApplicability.catalog_id == VehicleCatalog.id)
        .outerjoin(Manual, Manual.id == ManualApplicability.manual_id)
        .where(VehicleCatalog.status != CatalogStatus.ARCHIVED)
        .group_by(VehicleCatalog.id)
        .order_by(VehicleCatalog.created_at.desc())
    ).all()
    return [catalog_response(catalog, count) for catalog, count in rows]


@router.post(
    "/vehicle-catalog",
    response_model=AdminVehicleCatalogResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_catalog(
    payload: AdminVehicleCatalogCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminVehicleCatalogResponse:
    manufacturer = payload.manufacturer.strip().upper()
    model_name = payload.model_name.strip()
    catalog = VehicleCatalog(
        id=uuid4(),
        manufacturer=manufacturer,
        model_name=model_name,
        model_year=payload.model_year,
        display_name=f"{model_name} {payload.model_year}",
        official_manual_url=str(payload.official_manual_url) if payload.official_manual_url else None,
        status=CatalogStatus.DRAFT,
        created_by=current_user.id,
    )
    db.add(catalog)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DUPLICATE_VEHICLE", "message": "이미 등록된 차량과 연식입니다."},
        ) from exc
    db.refresh(catalog)
    return catalog_response(catalog)


@router.patch("/vehicle-catalog/{catalog_id}", response_model=AdminVehicleCatalogResponse)
def update_admin_catalog(
    catalog_id: UUID,
    payload: AdminVehicleCatalogUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminVehicleCatalogResponse:
    catalog = db.get(VehicleCatalog, catalog_id)
    if catalog is None or catalog.status == CatalogStatus.ARCHIVED:
        raise HTTPException(status_code=404, detail="차량을 찾을 수 없습니다.")
    if catalog.status != CatalogStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CATALOG_NOT_EDITABLE", "message": "초안 상태의 차량만 수정할 수 있습니다."},
        )
    catalog.manufacturer = payload.manufacturer.strip().upper()
    catalog.model_name = payload.model_name.strip()
    catalog.model_year = payload.model_year
    catalog.display_name = f"{catalog.model_name} {catalog.model_year}"
    catalog.official_manual_url = str(payload.official_manual_url) if payload.official_manual_url else None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DUPLICATE_VEHICLE", "message": "이미 등록된 차량과 연식입니다."},
        ) from exc
    db.refresh(catalog)
    return catalog_response(catalog)


@router.patch("/vehicle-catalog/{catalog_id}/official-manual-url", response_model=AdminVehicleCatalogResponse)
def update_catalog_official_manual_url(
    catalog_id: UUID,
    payload: OfficialManualUrlUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminVehicleCatalogResponse:
    """Save an admin-verified Hyundai manual root URL for any live catalog.

    This is navigation metadata, not a request to scrape protected web pages.
    It deliberately remains editable after the representative PDF activates a
    catalog because Hyundai may change a web-manual route independently.
    """
    catalog = db.get(VehicleCatalog, catalog_id)
    if catalog is None or catalog.status == CatalogStatus.ARCHIVED:
        raise HTTPException(status_code=404, detail="차량을 찾을 수 없습니다.")
    catalog.official_manual_url = str(payload.official_manual_url) if payload.official_manual_url else None
    db.commit()
    db.refresh(catalog)
    return catalog_response(catalog)


@router.get(
    "/vehicle-catalog/{catalog_id}/official-sources",
    response_model=list[OfficialSourceResponse],
)
def list_official_sources(
    catalog_id: UUID,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[OfficialSourceResponse]:
    catalog = db.get(VehicleCatalog, catalog_id)
    if catalog is None or catalog.status == CatalogStatus.ARCHIVED:
        raise HTTPException(status_code=404, detail="차량을 찾을 수 없습니다.")
    return [official_source_response(source) for source in resolve_official_sources(db, catalog_id)]


@router.post(
    "/vehicle-catalog/{catalog_id}/official-sources/sync",
    response_model=OfficialSourceSyncResponse,
)
async def sync_catalog_official_sources(
    catalog_id: UUID,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OfficialSourceSyncResponse:
    catalog = db.get(VehicleCatalog, catalog_id)
    if catalog is None or catalog.status == CatalogStatus.ARCHIVED:
        raise HTTPException(status_code=404, detail="차량을 찾을 수 없습니다.")
    try:
        sources = await sync_official_sources(db, catalog)
    except OfficialSourceSyncError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return OfficialSourceSyncResponse(
        catalog_id=catalog.id,
        synced_count=len(sources),
        sources=[official_source_response(source) for source in sources],
    )


@router.delete("/vehicle-catalog/{catalog_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_admin_catalog(
    catalog_id: UUID,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    catalog = db.get(VehicleCatalog, catalog_id)
    if catalog is None or catalog.status == CatalogStatus.ARCHIVED:
        raise HTTPException(status_code=404, detail="차량을 찾을 수 없습니다.")
    if catalog.status != CatalogStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CATALOG_NOT_DELETABLE", "message": "초안 상태의 차량만 삭제할 수 있습니다."},
        )
    catalog.status = CatalogStatus.ARCHIVED
    db.commit()


@router.post("/manuals", response_model=ManualResponse, status_code=status.HTTP_201_CREATED)
def create_manual(
    payload: ManualCreateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ManualResponse:
    catalog_ids = list(dict.fromkeys(payload.catalog_ids))
    primary_ids = set(payload.primary_catalog_ids)
    if not primary_ids.issubset(set(catalog_ids)):
        raise HTTPException(status_code=422, detail="대표 매뉴얼 대상은 적용 차량 안에서 선택해야 합니다.")
    catalogs = list(db.scalars(select(VehicleCatalog).where(VehicleCatalog.id.in_(catalog_ids))))
    if len(catalogs) != len(catalog_ids):
        raise HTTPException(status_code=404, detail="적용 차량을 찾을 수 없습니다.")

    manual_id = uuid4()
    clean_filename = re.sub(r"[^A-Za-z0-9._-]", "_", payload.original_filename)
    manual = Manual(
        id=manual_id,
        title=payload.title.strip(),
        manual_type=payload.manual_type.strip().upper(),
        locale=payload.locale.strip(),
        source_url=str(payload.source_url) if payload.source_url else None,
        object_key=f"staging/manuals/{manual_id}/{clean_filename}",
        original_filename=payload.original_filename,
        sha256=payload.sha256.lower(),
        file_size_bytes=payload.file_size_bytes,
        pdf_page_count=0,
        status=ManualStatus.DRAFT,
        created_by=current_user.id,
    )
    db.add(manual)
    for catalog_id in catalog_ids:
        db.add(
            ManualApplicability(
                manual_id=manual_id,
                catalog_id=catalog_id,
                is_primary=catalog_id in primary_ids,
            )
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "MANUAL_CONFLICT", "message": "이미 연결된 대표 매뉴얼 또는 동일 파일입니다."},
        ) from exc
    db.refresh(manual)
    return manual_response(manual, catalogs, primary_ids)


@router.get("/manuals", response_model=list[ManualResponse])
def list_manuals(
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[ManualResponse]:
    manuals = list(
        db.scalars(
            select(Manual)
            .where(Manual.status != ManualStatus.ARCHIVED)
            .order_by(Manual.uploaded_at.desc().nullslast())
        )
    )
    result: list[ManualResponse] = []
    for manual in manuals:
        catalogs = list(
            db.scalars(
                select(VehicleCatalog)
                .join(ManualApplicability, ManualApplicability.catalog_id == VehicleCatalog.id)
                .where(ManualApplicability.manual_id == manual.id)
                .order_by(VehicleCatalog.display_name)
            )
        )
        primary_ids = list(
            db.scalars(
                select(ManualApplicability.catalog_id).where(
                    ManualApplicability.manual_id == manual.id,
                    ManualApplicability.is_primary.is_(True),
                )
            )
        )
        result.append(manual_response(manual, catalogs, primary_ids))
    return result


@router.patch("/manuals/{manual_id}", response_model=ManualResponse)
def update_manual(
    manual_id: UUID,
    payload: ManualUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ManualResponse:
    manual = db.get(Manual, manual_id)
    if manual is None or manual.status == ManualStatus.ARCHIVED:
        raise HTTPException(status_code=404, detail="매뉴얼을 찾을 수 없습니다.")
    if manual.status not in {ManualStatus.DRAFT, ManualStatus.UPLOADED, ManualStatus.FAILED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "MANUAL_NOT_EDITABLE", "message": "적재 중이거나 공개된 매뉴얼은 수정할 수 없습니다."},
        )
    catalog_ids = list(dict.fromkeys(payload.catalog_ids))
    primary_ids = set(payload.primary_catalog_ids)
    if not primary_ids.issubset(set(catalog_ids)):
        raise HTTPException(status_code=422, detail="대표 매뉴얼 대상은 적용 차량 안에서 선택해야 합니다.")
    catalogs = list(db.scalars(select(VehicleCatalog).where(VehicleCatalog.id.in_(catalog_ids))))
    if len(catalogs) != len(catalog_ids) or any(catalog.status == CatalogStatus.ARCHIVED for catalog in catalogs):
        raise HTTPException(status_code=404, detail="적용 차량을 찾을 수 없습니다.")

    db.query(ManualApplicability).filter(ManualApplicability.manual_id == manual.id).delete()
    manual.title = payload.title.strip()
    manual.manual_type = payload.manual_type.strip().upper()
    manual.locale = payload.locale.strip()
    for catalog_id in catalog_ids:
        db.add(
            ManualApplicability(
                manual_id=manual.id,
                catalog_id=catalog_id,
                is_primary=catalog_id in primary_ids,
            )
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "MANUAL_CONFLICT", "message": "이미 연결된 대표 매뉴얼이 있습니다."},
        ) from exc
    db.refresh(manual)
    return manual_response(manual, catalogs, primary_ids)


@router.delete("/manuals/{manual_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_manual(
    manual_id: UUID,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    manual = db.get(Manual, manual_id)
    if manual is None or manual.status == ManualStatus.ARCHIVED:
        raise HTTPException(status_code=404, detail="매뉴얼을 찾을 수 없습니다.")
    # 보관된 문서는 더 이상 차량 공개 조건을 충족하거나 대표 매뉴얼 자리를 점유하지 않는다.
    db.query(ManualApplicability).filter(ManualApplicability.manual_id == manual.id).update(
        {ManualApplicability.is_primary: False}, synchronize_session=False
    )
    manual.status = ManualStatus.ARCHIVED
    db.commit()


@router.post("/manuals/{manual_id}/upload-url", response_model=UploadUrlResponse)
def get_manual_upload_url(
    manual_id: UUID,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UploadUrlResponse:
    manual = db.get(Manual, manual_id)
    if manual is None:
        raise HTTPException(status_code=404, detail="매뉴얼을 찾을 수 없습니다.")
    if manual.status not in {ManualStatus.DRAFT, ManualStatus.FAILED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "MANUAL_STATE_CONFLICT", "message": "현재 상태에서는 파일을 업로드할 수 없습니다."},
        )
    storage = PrivateStorage(get_settings())
    try:
        upload_url = storage.create_upload_url(manual.object_key, manual.sha256)
    except ClientError as exc:
        raise HTTPException(status_code=503, detail="파일 저장소에 연결할 수 없습니다.") from exc
    return UploadUrlResponse(
        upload_url=upload_url,
        expires_in=get_settings().upload_url_ttl_seconds,
        required_headers={
            "Content-Type": "application/pdf",
            "x-amz-meta-sha256": manual.sha256,
        },
    )


@router.post("/manuals/{manual_id}/upload-complete", response_model=UploadCompleteResponse)
def complete_manual_upload(
    manual_id: UUID,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UploadCompleteResponse:
    manual = db.get(Manual, manual_id)
    if manual is None:
        raise HTTPException(status_code=404, detail="매뉴얼을 찾을 수 없습니다.")
    if manual.status not in {ManualStatus.DRAFT, ManualStatus.FAILED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "MANUAL_STATE_CONFLICT", "message": "이미 처리 중이거나 완료된 매뉴얼입니다."},
        )
    try:
        page_count = PrivateStorage(get_settings()).validate_pdf(
            manual.object_key, manual.file_size_bytes, manual.sha256
        )
    except (ClientError, ValueError) as exc:
        manual.status = ManualStatus.FAILED
        manual.ingestion_error = str(exc)
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    manual.status = ManualStatus.UPLOADED
    manual.pdf_page_count = page_count
    manual.uploaded_at = datetime.now(UTC)
    manual.ingestion_error = None
    db.commit()
    return UploadCompleteResponse(id=manual.id, status=manual.status, pdf_page_count=page_count)


@router.post("/manuals/{manual_id}/prepare-rag-test", response_model=ManualIndexResponse)
def prepare_manual_rag_test(
    manual_id: UUID,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ManualIndexResponse:
    """Extract and chunk an uploaded PDF, then expose it to the local user RAG test."""
    manual = db.get(Manual, manual_id)
    if manual is None or manual.status == ManualStatus.ARCHIVED:
        raise HTTPException(status_code=404, detail="매뉴얼을 찾을 수 없습니다.")
    try:
        page_count, chunk_count = prepare_manual_for_indexing(db, manual)
    except (ClientError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="문서 테스트 준비 중 오류가 발생했습니다.") from exc
    background_tasks.add_task(embed_manual_in_background, manual_id)
    return ManualIndexResponse(
        id=manual_id, status=ManualStatus.INDEXING, indexed_page_count=page_count,
        indexing_total_chunks=chunk_count, embedded_chunk_count=0,
    )


@router.post("/manuals/{manual_id}/rebuild-rag-index", response_model=ManualIndexResponse)
def rebuild_manual_rag_index(
    manual_id: UUID,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ManualIndexResponse:
    """Re-extract and re-embed an existing READY PDF after RAG changes."""
    manual = db.get(Manual, manual_id)
    if manual is None or manual.status == ManualStatus.ARCHIVED:
        raise HTTPException(status_code=404, detail="매뉴얼을 찾을 수 없습니다.")
    try:
        page_count, chunk_count = prepare_manual_for_indexing(db, manual, force=True)
    except (ClientError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="임베딩 재생성 중 오류가 발생했습니다.") from exc
    background_tasks.add_task(embed_manual_in_background, manual_id)
    return ManualIndexResponse(
        id=manual_id, status=ManualStatus.INDEXING, indexed_page_count=page_count,
        indexing_total_chunks=chunk_count, embedded_chunk_count=0,
    )


def manual_response(
    manual: Manual, catalogs: list[VehicleCatalog], primary_catalog_ids: set[UUID] | list[UUID]
) -> ManualResponse:
    return ManualResponse(
        id=manual.id,
        title=manual.title,
        manual_type=manual.manual_type,
        locale=manual.locale,
        status=manual.status,
        original_filename=manual.original_filename,
        file_size_bytes=manual.file_size_bytes,
        pdf_page_count=manual.pdf_page_count,
        catalog_ids=[catalog.id for catalog in catalogs],
        primary_catalog_ids=list(primary_catalog_ids),
        applicable_catalogs=[catalog.display_name for catalog in catalogs],
        uploaded_at=manual.uploaded_at,
        ingestion_error=manual.ingestion_error,
        indexing_total_chunks=manual.indexing_total_chunks,
        embedded_chunk_count=manual.embedded_chunk_count,
    )


def official_source_response(source) -> OfficialSourceResponse:
    return OfficialSourceResponse(
        id=source.id,
        source_type=source.source_type,
        system_variant=source.system_variant,
        title=source.title,
        source_url=source.source_url,
        status=source.status,
        synced_at=source.synced_at,
    )
