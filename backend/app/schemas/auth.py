from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models import UserRole


class UserResponse(BaseModel):
    id: UUID
    display_name: str
    role: UserRole
    onboarding_completed: bool
    created_at: datetime


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserResponse


class OnboardingRequest(BaseModel):
    role: UserRole
    admin_code: str | None = Field(default=None, max_length=256)
