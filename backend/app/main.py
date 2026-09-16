from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.router import router
from app.core.config import get_settings

settings = get_settings()

tags_metadata = [
    {
        "name": "system",
        "description": "서비스 상태 확인 API입니다.",
    },
    {
        "name": "auth",
        "description": "카카오 OAuth와 JWT 세션 API입니다.",
    },
    {
        "name": "vehicles",
        "description": "차량 카탈로그와 내 차량 관리 API입니다.",
    },
    {
        "name": "chat-sessions",
        "description": "선택 차량 매뉴얼 기반의 비영구 단기 상담 API입니다.",
    },
    {
        "name": "admin-vehicle-catalog",
        "description": "관리자 전용 차량 카탈로그와 공식 소스 운영 API입니다.",
    },
    {
        "name": "admin-manuals",
        "description": "관리자 전용 PDF 매뉴얼 업로드와 RAG 인덱싱 운영 API입니다.",
    },
]

app = FastAPI(
    title=settings.app_name,
    summary="선택 차량 매뉴얼 기반 RAG 상담 API",
    description=(
        "차량 선택으로 적용 매뉴얼을 결정하고, 매뉴얼 내부의 목차 섹션과 "
        "페이지 청크를 검색해 근거 기반 답변을 반환합니다. "
        "상세 계약은 `docs/api_명세서.md`를 따릅니다."
    ),
    version="0.1.0",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    openapi_tags=tags_metadata,
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
    },
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_v1_prefix)


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        summary=app.summary,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})[
        "bearerAuth"
    ] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "`POST /auth/access-token`에서 받은 access JWT를 입력합니다.",
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
