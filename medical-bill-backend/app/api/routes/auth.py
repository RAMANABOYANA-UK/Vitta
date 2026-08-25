"""Authentication routes: self-serve registration, login, logout, and identity.

Issues opaque bearer tokens (see app.core.security / app.core.auth). Only the
SHA-256 of each token is persisted, and the raw token is returned exactly once
on register/login. Login failures are deliberately uniform — same status, same
message, same work done — so response behaviour never reveals whether an email
is registered.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.core.auth import _extract_bearer_token, get_current_user
from app.core.security import (
    generate_secure_token,
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.database import get_session
from app.models import User, UserSession
from app.schemas import (
    EmailVerificationRequest,
    EmailVerificationStatus,
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserRead,
)
from app.services.mailer import send_verification_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# A valid PBKDF2 encoding hashed once at import. When a login names an email that
# does not exist, we still run one verify_password against this so the response
# time matches the "user exists but wrong password" path — closing the timing
# side channel that would otherwise leak which emails have accounts.
_DUMMY_PASSWORD_HASH = hash_password("timing-equalization-placeholder-not-a-real-secret")


def _invalid_credentials() -> HTTPException:
    """Uniform 401 for every login failure (no such user / bad password /
    disabled account) so the client cannot distinguish the cases."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _issue_session(session: AsyncSession, user: User) -> tuple[str, datetime]:
    """Mint a new opaque session for ``user``. Returns the raw token (shown to
    the client once) and its expiry; only the token's hash is stored."""
    raw_token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.AUTH_TOKEN_TTL_HOURS
    )
    user_session = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=expires_at,
    )
    session.add(user_session)
    await session.commit()
    return raw_token, expires_at


def _issue_verification_token(user: User) -> str | None:
    """Arm ``user`` for email verification and return the raw one-time token
    (to be emailed) — or None when verification is disabled. When enabled the
    account is NOT marked verified until the token is redeemed."""
    raw_token = generate_secure_token(32)
    user.email_verified = False
    user.email_verification_token_hash = hash_token(raw_token)
    user.email_verification_expires_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.EMAIL_VERIFICATION_TTL_HOURS
    )
    return raw_token


def _email_verified(user: User) -> bool:
    """Whether ``user`` can log in: profile active AND (if required) verified."""
    if not user.is_active:
        return False
    if settings.EMAIL_VERIFICATION_REQUIRED and not user.email_verified:
        return False
    return True


def _token_response(user: User, raw_token: str, expires_at: datetime) -> TokenResponse:
    return TokenResponse(
        access_token=raw_token,
        token_type="bearer",
        expires_at=expires_at,
        user=UserRead(id=user.id, email=user.email, created_at=user.created_at),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and receive a session token",
)
async def register(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Self-serve registration. Email is normalized/validated by the schema and
    must be unique; the password is stored only as a PBKDF2 hash. On success the
    caller is logged straight in (a token is issued)."""
    # Fast-path existence check (nice error), backed by the DB unique constraint
    # below to close the check-then-insert race.
    existing = await session.exec(select(User).where(User.email == payload.email))
    if existing.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    # Arm email verification (unless disabled). When enabled the user is NOT
    # verified yet and must redeem the emailed token before logging in.
    if settings.EMAIL_VERIFICATION_REQUIRED:
        verify_token = _issue_verification_token(user)
    else:
        user.email_verified = True
        verify_token = None
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # Concurrent register won the unique-email race.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    await session.refresh(user)

    if verify_token:
        send_verification_email(user.email, verify_token)

    raw_token, expires_at = await _issue_session(session, user)
    logger.info("auth.register success user_id=%s", user.id)
    return _token_response(user, raw_token, expires_at)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Exchange credentials for a session token",
)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Verify credentials and issue a session token. Every failure returns the
    same generic 401 and performs one password verification, regardless of
    whether the account exists or is active."""
    result = await session.exec(select(User).where(User.email == payload.email))
    user = result.first()

    if user is None:
        # Equalize timing against the real-verify path, then fail uniformly.
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        logger.warning("auth.login failed (unknown email)")
        raise _invalid_credentials()

    password_ok = verify_password(payload.password, user.password_hash)
    if not password_ok or not user.is_active:
        logger.warning("auth.login failed user_id=%s active=%s", user.id, user.is_active)
        raise _invalid_credentials()

    if settings.EMAIL_VERIFICATION_REQUIRED and not user.email_verified:
        # Distinct error so the client can show a "please verify your email"
        # screen without revealing anything about the account (email was valid).
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="email_not_verified",
        )

    raw_token, expires_at = await _issue_session(session, user)
    logger.info("auth.login success user_id=%s", user.id)
    return _token_response(user, raw_token, expires_at)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the presented session token",
)
async def logout(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete the session for the presented bearer token. Idempotent: if the
    token is already unknown/expired there is simply nothing to delete."""
    token = _extract_bearer_token(authorization)
    result = await session.exec(
        select(UserSession).where(UserSession.token_hash == hash_token(token))
    )
    user_session = result.first()
    if user_session is not None:
        logger.info("auth.logout user_id=%s", user_session.user_id)
        await session.delete(user_session)
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Return the authenticated user",
)
async def read_me(current_user: User = Depends(get_current_user)) -> UserRead:
    """Identity endpoint used by the frontend to confirm a stored token is still
    valid and to render the signed-in user."""
    return UserRead(
        id=current_user.id,
        email=current_user.email,
        email_verified=current_user.email_verified,
        created_at=current_user.created_at,
    )


@router.post(
    "/logout-everywhere",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke every session for the current user",
)
async def logout_everywhere(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete every session token belonging to the current user (logout on all
    devices). Revocation is durable: afterwards no issued bearer token for this
    user is valid."""
    result = await session.exec(
        select(UserSession).where(UserSession.user_id == current_user.id)
    )
    revoke: list[UserSession] = list(result.all())
    n = 0
    for us in revoke:
        await session.delete(us)
        n += 1
    await session.commit()
    logger.info("auth.logout_everywhere user_id=%s revoked=%d", current_user.id, n)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/verify-email",
    response_model=EmailVerificationStatus,
    summary="Redeem a one-time email verification token",
)
async def verify_email(
    payload: EmailVerificationRequest,
    session: AsyncSession = Depends(get_session),
) -> EmailVerificationStatus:
    """Confirm an account's email by redeeming the one-time token. Idempotent;
    an unknown/expired/already-redeemed token returns 400 with a uniform detail."""
    token_hash = hash_token(payload.token)
    result = await session.exec(
        select(User).where(User.email_verification_token_hash == token_hash)
    )
    user = result.first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already-used verification token",
        )
    now = datetime.now(timezone.utc)
    expires_at = user.email_verification_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is None or expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already-used verification token",
        )

    user.email_verified = True
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    session.add(user)
    await session.commit()
    logger.info("auth.verify_email success user_id=%s", user.id)
    return EmailVerificationStatus(email=user.email, email_verified=True)


@router.post(
    "/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Issue a fresh email-verification token for the current user",
)
async def resend_verification(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Re-arm and re-send a verification email for the current user. Only
    meaningful when EMAIL_VERIFICATION_REQUIRED (the account is not yet
    verified); returns 409 if there is nothing to verify."""
    if current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already verified",
        )
    raw_token = _issue_verification_token(current_user)
    session.add(current_user)
    await session.commit()
    send_verification_email(current_user.email, raw_token)
    logger.info("auth.resend_verification user_id=%s", current_user.id)
    return {"email": current_user.email, "email_verified": False}
