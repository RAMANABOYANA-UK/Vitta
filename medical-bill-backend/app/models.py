from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import DateTime, func
import uuid

from app.schemas import DocumentStatus


def _uuid() -> str:
    return str(uuid.uuid4())


class User(SQLModel, table=True):
    """An account that owns uploaded documents. Self-serve registration."""

    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True)
    email: str = Field(index=True, unique=True)
    # PBKDF2 encoding produced by app.core.security.hash_password — never a raw password.
    password_hash: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
        )
    )


class UserSession(SQLModel, table=True):
    """An opaque bearer-token session. Only the SHA-256 of the token is stored;
    the raw token is shown to the client exactly once at login/register."""

    __tablename__ = "sessions"

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(index=True, unique=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    # Set in application code (now + AUTH_TOKEN_TTL_HOURS); compared on every request.
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True)))


class AccessLog(SQLModel, table=True):
    """Append-only audit trail: who touched which document, and how. Both a
    compliance record and the real data source for the frontend timeline."""

    __tablename__ = "access_logs"

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(index=True)
    document_id: Optional[str] = Field(default=None, index=True)
    action: str  # e.g. "upload", "read", "status", "update_letter", "reprocess"
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class Document(SQLModel, table=True):
    """Database model for an uploaded medical bill document."""

    __tablename__ = "documents"

    id: str = Field(default_factory=_uuid, primary_key=True)
    # Nullable so create_all against a pre-existing documents table does not fail;
    # every new upload sets it, and reads are scoped to the owner.
    owner_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)
    original_filename: str
    storage_key: str
    content_type: str
    status: str = Field(
        default=DocumentStatus.uploaded.value
    )
    result_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    error_message: Optional[str] = None
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
        )
    )
