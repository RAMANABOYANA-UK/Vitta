"""Authentication dependencies for FastAPI routes.

Resolves an opaque bearer token to the owning :class:`~app.models.User` by
hashing the presented token and matching it against an unexpired
:class:`~app.models.UserSession`. Also exposes an upload rate-limit dependency
that layers a per-user ceiling on top of authentication.

Design notes:
  * Tokens are opaque and server-side. The DB stores only ``sha256(token)``
    (see app.core.security.hash_token), so lookups hash the incoming token and
    match on the digest; a leaked DB cannot mint or replay sessions.
  * Every failure path raises the *same* generic 401 so an attacker cannot tell
    a missing header from a bad/expired token from a disabled user.
  * Expired sessions are deleted on encounter (lazy cleanup) so the table does
    not accumulate dead rows purely through normal traffic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.core.ratelimit import InMemoryRateLimiter
from app.core.security import hash_token
from app.database import get_session
from app.models import User, UserSession


def _unauthorized() -> HTTPException:
    """A fresh, deliberately generic 401. Constructed per-raise so no shared
    mutable exception state leaks across requests."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_bearer_token(authorization: Optional[str]) -> str:
    """Pull the raw token out of an ``Authorization: Bearer <token>`` header,
    or raise 401 if the header is absent/malformed."""
    if not authorization:
        raise _unauthorized()
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise _unauthorized()
    token = token.strip()
    if not token:
        raise _unauthorized()
    return token


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """FastAPI dependency: authenticate the caller from the bearer token.

    Raises a generic 401 if the token is missing, unknown, expired, or belongs
    to a disabled/deleted user. Returns the live :class:`User` otherwise.
    """
    token = _extract_bearer_token(authorization)
    token_hash = hash_token(token)

    result = await session.exec(
        select(UserSession).where(UserSession.token_hash == token_hash)
    )
    user_session = result.first()
    if user_session is None:
        raise _unauthorized()

    # expires_at is stored tz-aware; coerce defensively in case a backend hands
    # back a naive datetime (SQLite can), then compare in UTC.
    expires_at = user_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        # Lazy cleanup of the expired session, then reject.
        await session.delete(user_session)
        await session.commit()
        raise _unauthorized()

    user = await session.get(User, user_session.user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


# ---------------------------------------------------------------------------
# Upload rate limiting
# ---------------------------------------------------------------------------
# Process-local limiter shared by all requests in this worker. See
# app.core.ratelimit for the multi-worker caveat (needs Redis in production).
_upload_rate_limiter = InMemoryRateLimiter(
    max_events=settings.UPLOAD_RATE_LIMIT_PER_MINUTE,
    window_seconds=60.0,
)


async def require_upload_slot(
    current_user: User = Depends(get_current_user),
) -> User:
    """Authenticate, then consume one upload slot for this user. Raises 429 when
    the per-user per-minute ceiling is exceeded. Returns the authenticated user
    so upload routes can depend on this directly in place of get_current_user."""
    if not _upload_rate_limiter.allow(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Upload rate limit exceeded "
                f"({settings.UPLOAD_RATE_LIMIT_PER_MINUTE} per minute). "
                f"Please wait a moment and try again."
            ),
        )
    return current_user
