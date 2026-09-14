from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["system"], summary="API 상태 확인")
def health() -> dict[str, str]:
    return {"status": "ok"}
