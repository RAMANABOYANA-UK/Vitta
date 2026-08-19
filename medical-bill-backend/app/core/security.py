"""
Security utilities for the medical bill platform.

Provides:
- Storage key generation, filename sanitization
- Bearer-token auth supporting both static AUTH_TOKEN and JWT
- JWT create/decode helpers
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def generate_storage_key(original_filename: str) -> str:
    """
    Generate a safe, unique storage key for an uploaded file.

    Format: {uuid4}/{sanitized_original_filename}
    Prevents path traversal and collisions while retaining context.
    """
    sanitized = Path(original_filename).name.replace(" ", "_")
    return f"{uuid.uuid4()}/{sanitized}"


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal attacks."""
    return Path(filename).name


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


def verify_bearer_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> None:
    """
    Verify the bearer token on protected endpoints.

    When AUTH_ENABLED=false, this dependency is a no-op (dev mode).
    When AUTH_ENABLED=true, requests must include:
        Authorization: Bearer <AUTH_TOKEN>
        -or-
        Authorization: Bearer <JWT>

    JWT tokens are issued via POST /api/v1/auth/token.
    """
    if not settings.AUTH_ENABLED:
        return

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # 1) Static dev token
    if secrets.compare_digest(token, settings.AUTH_TOKEN):
        return

    # 2) JWT
    try:
        decode_jwt_token(token)
        return
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_jwt_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    """Create a JWT token (requires PyJWT installed)."""
    import jwt

    secret = settings.JWT_SECRET or settings.AUTH_TOKEN
    expires = expires_minutes or settings.JWT_EXPIRES_MINUTES
    payload = {
        "sub": subject,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires),
    }
    return jwt.encode(payload, secret, algorithm=settings.JWT_ALGORITHM)


def decode_jwt_token(token: str) -> dict:
    """Decode and validate a JWT token (requires PyJWT installed)."""
    import jwt

    secret = settings.JWT_SECRET or settings.AUTH_TOKEN
    return jwt.decode(token, secret, algorithms=[settings.JWT_ALGORITHM])