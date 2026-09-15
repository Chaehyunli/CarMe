from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api.vehicle_catalog import active_catalog_statement, get_db
from app.db.models import CatalogStatus, VehicleCatalog
from app.main import app


class FakeResult:
    def __init__(self, rows: list[VehicleCatalog]) -> None:
        self.rows = rows

    def scalars(self) -> "FakeResult":
        return self

    def __iter__(self):
        return iter(self.rows)


class FakeSession:
    def __init__(self, rows: list[VehicleCatalog]) -> None:
        self.rows = rows
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return FakeResult(self.rows)


def test_active_catalog_statement_limits_primary_ready_manuals() -> None:
    statement = active_catalog_statement()

    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "vehicle_catalogs.status" in compiled
    assert "manual_applicabilities.is_primary IS true" in compiled
    assert "manuals.status" in compiled


def test_list_vehicle_catalog_returns_display_fields_only() -> None:
    catalog = VehicleCatalog(
        id=uuid4(),
        manufacturer="HYUNDAI",
        model_name="아반떼",
        model_year=2025,
        display_name="아반떼 2025",
        status=CatalogStatus.ACTIVE,
        created_by=uuid4(),
    )
    fake_session = FakeSession([catalog])
    app.dependency_overrides[get_db] = lambda: fake_session
    client = TestClient(app)

    try:
        response = client.get("/api/v1/vehicle-catalog")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(catalog.id),
            "manufacturer": "HYUNDAI",
            "model_name": "아반떼",
            "model_year": 2025,
            "display_name": "아반떼 2025",
            "status": "ACTIVE",
        }
    ]
    assert fake_session.statement is not None
