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
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.database import get_session
from app.models import User, UserSession
from app.schemas import LoginRequest, TokenResponse, UserCreate, UserRead

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
        created_at=current_user.created_at,
    )
