import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr
from app.models.user import UserTier


class UserBase(BaseModel):
    email: EmailStr
    tier: UserTier = UserTier.starter
    videos_used: int = 0
    onboarding_completed_at: datetime | None = None
    onboarding_skipped_at: datetime | None = None
    onboarding_role: str | None = None
    onboarding_metadata_json: dict | None = None
    billing_plan: str = "trial"
    subscription_status: str = "trialing"
    trial_ends_at: datetime | None = None
    is_beta_tester: bool = False
    beta_expires_at: datetime | None = None
    beta_welcome_seen_at: datetime | None = None
    billing_period_start: datetime | None = None
    billing_period_end: datetime | None = None
    platforms_allowed: int = 5
    caption_preset: str | None = None
    caption_style: str | None = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserResponse(UserBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    beta_access_code: str | None = None


class BetaActivationRequest(BaseModel):
    beta_access_code: str


class SignupResponse(BaseModel):
    message: str
    user: UserResponse


class UpdateEmailRequest(BaseModel):
    new_email: EmailStr
    current_password: str


class UpdateEmailResponse(BaseModel):
    message: str
    user: UserResponse


class UpdatePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class MessageResponse(BaseModel):
    message: str


class DeleteAccountRequest(BaseModel):
    current_password: str
    confirm_text: str
