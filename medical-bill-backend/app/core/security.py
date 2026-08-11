"""
Security utilities for the medical bill platform.

Phase 1 provides foundational helpers (random token generation, safe filenames).
Authentication and authorization will be layered in a later phase.
"""
import secrets
import uuid
from pathlib import Path


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