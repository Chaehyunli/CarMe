# ruff: noqa: B008
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import Settings, get_settings
from app.core.security import (
    create_access_token,
    create_oauth_state,
    new_refresh_token,
    token_hash,
    unauthorized,
    verify_oauth_state,
)
from app.db.models import RefreshToken, User, UserRole
from app.db.session import get_db
from app.schemas.auth import AccessTokenResponse, OnboardingRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "carme_refresh_token"


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        display_name=user.display_name,
        role=user.role,
        onboarding_completed=user.onboarding_completed,
        created_at=user.created_at,
    )


def frontend_redirect(settings: Settings, path: str, **params: str) -> RedirectResponse:
    query = urlencode(params)
    suffix = f"?{query}" if query else ""
    return RedirectResponse(f"{settings.frontend_login_callback_url.rsplit('/auth/callback', 1)[0]}{path}{suffix}")


def set_refresh_cookie(response: Response, refresh_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        max_age=settings.jwt_refresh_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.app_env != "local",
        samesite="lax",
        path=f"{settings.api_v1_prefix}/auth",
    )


@router.get("/kakao/start", summary="카카오 로그인 시작")
def start_kakao_login(settings: Settings = Depends(get_settings)) -> RedirectResponse:
    if not settings.kakao_rest_api_key or not settings.kakao_redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "KAKAO_NOT_CONFIGURED", "message": "카카오 로그인 설정이 필요합니다."},
        )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.kakao_rest_api_key,
            "redirect_uri": settings.kakao_redirect_uri,
            "state": create_oauth_state(settings),
        }
    )
    return RedirectResponse(f"https://kauth.kakao.com/oauth/authorize?{query}")


@router.get("/kakao/callback", summary="카카오 로그인 콜백")
async def kakao_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    try:
        verify_oauth_state(state, settings)
        token_payload = {
            "grant_type": "authorization_code",
            "client_id": settings.kakao_rest_api_key,
            "redirect_uri": settings.kakao_redirect_uri,
            "code": code,
        }
        if settings.kakao_client_secret:
            token_payload["client_secret"] = settings.kakao_client_secret
        async with httpx.AsyncClient(timeout=10) as client:
            token_response = await client.post(
                "https://kauth.kakao.com/oauth/token",
                data=token_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
            )
            token_response.raise_for_status()
            kakao_token = token_response.json()["access_token"]
            profile_response = await client.get(
                "https://kapi.kakao.com/v2/user/me",
                headers={"Authorization": f"Bearer {kakao_token}"},
            )
            profile_response.raise_for_status()
            profile = profile_response.json()
    except (HTTPException, httpx.HTTPError, KeyError):
        return frontend_redirect(settings, "/login", error="kakao_login_failed")

    kakao_subject = str(profile["id"])
    nickname = (
        profile.get("properties", {}).get("nickname")
        or profile.get("kakao_account", {}).get("profile", {}).get("nickname")
        or "CarMe 사용자"
    )
    user = db.scalar(select(User).where(User.kakao_subject == kakao_subject))
    if user is None:
        user = User(
            id=uuid4(),
            kakao_subject=kakao_subject,
            display_name=nickname[:100],
            role=UserRole.USER,
            onboarding_completed=False,
        )
        db.add(user)
        db.flush()

    refresh_value = new_refresh_token()
    db.add(
        RefreshToken(
            id=uuid4(),
            user_id=user.id,
            token_hash=token_hash(refresh_value),
            expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_ttl_days),
        )
    )
    db.commit()

    response = frontend_redirect(settings, "/auth/callback", login="success")
    set_refresh_cookie(response, refresh_value, settings)
    return response


@router.post("/access-token", response_model=AccessTokenResponse, summary="access JWT 발급")
def issue_access_token(
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccessTokenResponse:
    if not refresh_token:
        raise unauthorized()
    refresh = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash(refresh_token))
    )
    if refresh is None or refresh.revoked_at is not None or refresh.expires_at <= datetime.now(UTC):
        raise unauthorized()
    user = db.get(User, refresh.user_id)
    if user is None:
        raise unauthorized()
    return AccessTokenResponse(
        access_token=create_access_token(user, settings),
        expires_in=settings.jwt_access_ttl_minutes * 60,
        user=user_response(user),
    )


@router.get("/me", response_model=UserResponse, summary="현재 사용자 조회")
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return user_response(current_user)


@router.post("/onboarding", response_model=UserResponse, summary="첫 로그인 역할 선택")
def complete_onboarding(
    payload: OnboardingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    if current_user.onboarding_completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ONBOARDING_ALREADY_COMPLETED", "message": "역할 선택이 이미 완료되었습니다."},
        )
    if payload.role == UserRole.ADMIN and (
        not settings.admin_signup_code
        or not payload.admin_code
        or not secrets.compare_digest(payload.admin_code, settings.admin_signup_code)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "INVALID_ADMIN_CODE", "message": "관리자 코드가 올바르지 않습니다."},
        )
    current_user.role = payload.role
    current_user.onboarding_completed = True
    db.commit()
    db.refresh(current_user)
    return user_response(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="로그아웃")
def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    db: Session = Depends(get_db),
) -> Response:
    if refresh_token:
        refresh = db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash(refresh_token))
        )
        if refresh is not None:
            refresh.revoked_at = datetime.now(UTC)
            db.commit()
    response.delete_cookie(REFRESH_COOKIE, path=f"{get_settings().api_v1_prefix}/auth")
    return response
