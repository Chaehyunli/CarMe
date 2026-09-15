from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import CatalogStatus, Manual, ManualApplicability, ManualStatus, VehicleCatalog
from app.db.session import get_db
from app.schemas.vehicle_catalog import VehicleCatalogResponse

router = APIRouter(prefix="/vehicle-catalog", tags=["vehicles"])


def active_catalog_statement() -> Select[tuple[VehicleCatalog]]:
    """Return only publicly selectable models with a usable primary manual."""

    return (
        select(VehicleCatalog)
        .join(ManualApplicability, ManualApplicability.catalog_id == VehicleCatalog.id)
        .join(Manual, Manual.id == ManualApplicability.manual_id)
        .where(
            VehicleCatalog.status == CatalogStatus.ACTIVE,
            ManualApplicability.is_primary.is_(True),
            Manual.status == ManualStatus.READY,
        )
        .order_by(VehicleCatalog.manufacturer, VehicleCatalog.model_name, VehicleCatalog.model_year)
    )


@router.get("", summary="등록 가능한 차량 카탈로그 조회")
def list_vehicle_catalog(
    db: Annotated[Session, Depends(get_db)],
) -> list[VehicleCatalogResponse]:
    """Expose display values only; internal object-storage details never join this response."""

    return list(db.execute(active_catalog_statement()).scalars())
