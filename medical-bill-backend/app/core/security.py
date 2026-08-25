"""
Security utilities for the medical bill platform.

Provides storage-key/filename helpers plus password hashing and opaque
session-token helpers. Everything here is standard-library only (no external
crypto dependency) so it is portable and unit-testable in isolation.

Password hashing uses PBKDF2-HMAC-SHA256 with a per-password random salt, encoded
as a single self-describing string: ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``.
Session tokens are random, url-safe, and never stored in the clear — only their
SHA-256 hash is persisted, so a leaked database cannot be used to mint sessions.
"""
import base64
import hashlib
import hmac
import secrets
import uuid
from pathlib import Path

# PBKDF2 work factor. OWASP's 2023 guidance for PBKDF2-HMAC-SHA256 is >= 600,000
# iterations. Kept here (not in settings) so the crypto layer has no config
# dependency and stays trivially testable; callers may override per-call.
DEFAULT_PBKDF2_ITERATIONS = 600_000
_PBKDF2_ALGORITHM = "pbkdf2_sha256"


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
# Password hashing (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------
def hash_password(password: str, *, iterations: int = DEFAULT_PBKDF2_ITERATIONS) -> str:
    """Hash a password into a self-describing ``pbkdf2_sha256$...`` string.

    A fresh 16-byte random salt is generated per call, so hashing the same
    password twice yields different encodings.
    """
    if not password:
        raise ValueError("password must be a non-empty string")
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "{}${}${}${}".format(
        _PBKDF2_ALGORITHM,
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password against a ``pbkdf2_sha256$...`` encoding.

    Uses a constant-time comparison and never raises on malformed input
    (returns False instead), so callers can treat it as a pure predicate.
    """
    try:
        algorithm, iter_str, salt_b64, hash_b64 = encoded.split("$")
        if algorithm != _PBKDF2_ALGORITHM:
            return False
        iterations = int(iter_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError, AttributeError):
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected)


# ---------------------------------------------------------------------------
# Opaque session tokens
# ---------------------------------------------------------------------------
def generate_session_token(length: int = 32) -> str:
    """Return a fresh, url-safe opaque session token.

    This is the only time the raw token exists; it is handed to the client once
    and never stored server-side (see :func:`hash_token`).
    """
    return secrets.token_urlsafe(length)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of a session token.

    Only this digest is persisted. Lookups hash the presented bearer token and
    match on the digest, so the database never holds a usable credential.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
