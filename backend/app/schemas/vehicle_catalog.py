from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.models import CatalogStatus


class VehicleCatalogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    manufacturer: str
    model_name: str
    model_year: int
    display_name: str
    status: CatalogStatus
