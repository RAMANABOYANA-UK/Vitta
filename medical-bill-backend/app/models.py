from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import DateTime, func
import uuid

from app.schemas import DocumentStatus


class Document(SQLModel, table=True):
    """Database model for an uploaded medical bill document."""

    __tablename__ = "documents"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
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