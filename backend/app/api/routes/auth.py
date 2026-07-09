import secrets

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.schemas.user import (
    GoogleLoginRequest,
    LoginRequest,
    MessageResponse,
    DeleteAccountRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    UpdateEmailRequest,
    UpdateEmailResponse,
    UpdatePasswordRequest,
    UserResponse,
)
from app.api.deps import get_current_user

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(user_id: str) -> str:
    expiry = datetime.utcnow() + timedelta(hours=settings.jwt_expiry_hours)
    return jwt.encode(
        {"sub": user_id, "exp": expiry},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def _is_configured(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip()
    return bool(normalized) and normalized.lower() != "placeholder"


def _is_email_verified(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    return normalized in {"true", "1", "yes"}


def _new_user_trial_ends_at() -> datetime:
    return datetime.utcnow() + timedelta(days=7)


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not pwd_context.verify(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/auth/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    password = body.password or ""

    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    existing_result = await db.execute(select(User).where(func.lower(User.email) == email))
    existing_user = existing_result.scalar_one_or_none()
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    user = User(
        email=email,
        password_hash=pwd_context.hash(password),
        trial_ends_at=_new_user_trial_ends_at(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return SignupResponse(
        message="Account created successfully",
        user=UserResponse.model_validate(user),
    )


@router.post("/auth/google/login", response_model=TokenResponse)
async def google_login(body: GoogleLoginRequest, db: AsyncSession = Depends(get_db)):
    google_client_id = (settings.google_client_id or "").strip()
    if not _is_configured(google_client_id):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google login is not configured",
        )

    id_token = body.id_token.strip()
    if not id_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="id_token is required",
        )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
            )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to validate Google token",
        )

    if response.status_code != 200:
        detail = "Invalid or expired Google token"
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            safe_reason = payload.get("error_description") or payload.get("error")
            if isinstance(safe_reason, str) and safe_reason.strip():
                detail = safe_reason.strip()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )

    try:
        payload = response.json()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google token validation returned invalid payload",
        )

    audience = str(payload.get("aud") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    email_verified = _is_email_verified(payload.get("email_verified"))

    if audience != google_client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token audience mismatch",
        )
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account email is missing",
        )
    if not email_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account email is not verified",
        )

    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            password_hash=pwd_context.hash(secrets.token_urlsafe(48)),
            trial_ends_at=_new_user_trial_ends_at(),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.patch("/auth/me/email", response_model=UpdateEmailResponse)
async def update_email(
    body: UpdateEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_email = body.new_email.strip().lower()
    current_email = (current_user.email or "").strip().lower()

    if not pwd_context.verify(body.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if new_email == current_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New email must be different from current email",
        )

    existing_result = await db.execute(select(User).where(func.lower(User.email) == new_email))
    existing_user = existing_result.scalar_one_or_none()
    if existing_user is not None and existing_user.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    current_user.email = new_email
    await db.commit()
    await db.refresh(current_user)

    return UpdateEmailResponse(
        message="Email updated successfully",
        user=UserResponse.model_validate(current_user),
    )


@router.post("/auth/me/password", response_model=MessageResponse)
async def update_password(
    body: UpdatePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not pwd_context.verify(body.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if len(body.new_password or "") < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters",
        )

    current_user.password_hash = pwd_context.hash(body.new_password)
    await db.commit()

    return MessageResponse(message="Password updated successfully")


@router.post("/auth/me/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: DeleteAccountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.confirm_text != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation text must be DELETE",
        )

    if not pwd_context.verify(body.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    await db.delete(current_user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
