import re

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import date, datetime
from enum import Enum


class DocumentStatus(str, Enum):
    uploaded = "uploaded"
    processing = "processing"
    analyzed = "analyzed"
    letter_ready = "letter_ready"
    error = "error"


class Flag(BaseModel):
    type: str
    severity: str  # "info" | "warning" | "critical"
    message: str
    rule_id: Optional[str] = None
    shap_contribution: Optional[float] = None


class LineItem(BaseModel):
    id: str
    page: int = 1
    description: str
    cpt_hcpcs: Optional[str] = None
    icd10: List[str] = []
    units: float = 1.0
    charge_amount: float
    allowed_amount: Optional[float] = None
    paid_amount: Optional[float] = None
    patient_responsibility: Optional[float] = None
    modifiers: List[str] = []
    flags: List[Flag] = []


class Totals(BaseModel):
    billed: float
    allowed: Optional[float] = None
    insurance_paid: Optional[float] = None
    patient_responsibility: Optional[float] = None
    potential_savings: Optional[float] = None


class AppealPrediction(BaseModel):
    success_probability: float
    confidence_interval: List[float]
    top_factors: List[str] = []
    model_version: Optional[str] = None


class Letter(BaseModel):
    status: str = "draft"  # "draft" | "verified" | "sent"
    content_markdown: str
    verified_fields: List[str] = []
    # Authoritative verification outcome, carried from letter_verifier.verify_letter.
    # Fail-closed default: a Letter constructed without an explicit result is
    # treated as NOT verified. `problems` is empty iff verification_passed is True.
    verification_passed: bool = False
    problems: List[str] = []


class ParsedBill(BaseModel):
    document_id: str
    status: DocumentStatus
    uploaded_at: datetime
    source_type: str
    patient: dict = {}
    provider: dict = {}
    payer: dict = {}
    service_date: Optional[date] = None
    line_items: List[LineItem] = []
    totals: Totals
    denial_codes: List[dict] = []
    appeal_prediction: Optional[AppealPrediction] = None
    explanation: Optional[str] = None
    letter: Optional[Letter] = None
    audit: dict = {}


# ---------- API request/response schemas ----------

class DocumentCreate(BaseModel):
    original_filename: str
    storage_key: str
    content_type: str


class DocumentResponse(BaseModel):
    id: str
    original_filename: str
    storage_key: str
    content_type: str
    status: DocumentStatus
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DocumentStatusResponse(BaseModel):
    id: str
    status: DocumentStatus
    error_message: Optional[str] = None
    updated_at: datetime


class DocumentDetailResponse(DocumentResponse):
    result: Optional[ParsedBill] = None


class LetterUpdateRequest(BaseModel):
    """Request body for PATCH /documents/{id}/letter.

    The server re-verifies the submitted letter against the underlying
    bill facts on every edit, so the content is constrained to be
    non-empty and of a reasonable maximum length.
    """

    content_markdown: str = Field(
        ...,
        min_length=1,
        max_length=64_000,
        description="Updated letter content in markdown format",
    )


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    dependencies: dict


# ---------- Auth schemas ----------

# Deliberately permissive email check done with a regex so we avoid the
# `email-validator` dependency (pydantic's EmailStr requires it).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    value = (value or "").strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("invalid email address")
    return value


class UserCreate(BaseModel):
    """Registration payload for POST /auth/register."""

    email: str
    password: str = Field(min_length=8, max_length=1024)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        return _normalize_email(v)


class LoginRequest(BaseModel):
    """Credentials for POST /auth/login."""

    email: str
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        # Normalize so login matches the stored (lowercased) address.
        return _normalize_email(v)


class UserRead(BaseModel):
    id: str
    email: str
    created_at: datetime


class TokenResponse(BaseModel):
    """Issued on register/login. `access_token` is the raw opaque token — the
    only time it is ever returned; the server stores only its hash."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserRead