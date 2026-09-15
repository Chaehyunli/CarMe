import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.core.config import Settings
from app.db.models import User, UserRole

ALGORITHM = "HS256"


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHENTICATED", "message": "인증이 필요합니다."},
    )


def create_access_token(user: User, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_oauth_state(settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "type": "oauth_state",
            "nonce": secrets.token_urlsafe(24),
            "iat": now,
            "exp": now + timedelta(minutes=10),
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )


def verify_oauth_state(value: str, settings: Settings) -> None:
    try:
        payload = jwt.decode(value, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise unauthorized() from exc
    if payload.get("type") != "oauth_state":
        raise unauthorized()


def decode_access_token(value: str, settings: Settings) -> tuple[UUID, UserRole]:
    try:
        payload = jwt.decode(value, settings.jwt_secret, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        return UUID(payload["sub"]), UserRole(payload["role"])
    except (JWTError, ValueError, KeyError) as exc:
        raise unauthorized() from exc


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_uuid() -> UUID:
    return uuid4()
