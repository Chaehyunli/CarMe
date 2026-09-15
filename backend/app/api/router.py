from fastapi import APIRouter

from app.api.vehicle_catalog import router as vehicle_catalog_router

router = APIRouter()


@router.get("/health", tags=["system"], summary="API 상태 확인")
def health() -> dict[str, str]:
    return {"status": "ok"}


router.include_router(vehicle_catalog_router)
