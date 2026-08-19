"""FastAPI application — exposes the three endpoints of the Data Extraction &
ML Models service.

Endpoints:
  POST /extract   — raw OCR text + layout JSON in → draft ParsedBill out
  POST /validate  — draft ParsedBill in → validated ParsedBill out
  POST /score     — validated ParsedBill in → scored ParsedBill out (with SHAP)

Each endpoint is independently callable and retryable. Validated results are
persisted to PostgreSQL (Neon/Supabase-compatible) when a DATABASE_URL is set.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.db import get_db
from app.models import DocumentStatus, ParsedBill
from app.services import (
    ExtractionRequest,
    ExtractionService,
    ScoringService,
    ValidationService,
    get_extraction_service,
    get_scoring_service,
    get_validation_service,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MedBills Data Extraction & ML Models Service",
    description=(
        "Turns raw OCR output into clean, validated, structured ParsedBill data. "
        "Downstream services trust the verified flags without re-checking."
    ),
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------
class ExtractRequest(BaseModel):
    """Input to /extract."""

    raw_ocr_text: str = Field(..., description="Raw OCR text from the document")
    layout_json: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Layout JSON (bounding boxes, tables) from the OCR engine",
    )
    document_id: Optional[str] = Field(
        default=None, description="Optional client-provided document ID"
    )


class ValidateRequest(BaseModel):
    """Input to /validate."""

    parsed_bill: ParsedBill = Field(..., description="Draft ParsedBill to validate")


class ScoreRequest(BaseModel):
    """Input to /score."""

    parsed_bill: ParsedBill = Field(
        ..., description="Validated ParsedBill to score"
    )


class HealthResponse(BaseModel):
    status: str
    llm_configured: bool
    database_connected: bool


# ---------------------------------------------------------------------------
# Service singletons (lazy)
# ---------------------------------------------------------------------------
_extraction_service: Optional[ExtractionService] = None
_validation_service: Optional[ValidationService] = None
_scoring_service: Optional[ScoringService] = None


def _get_extraction() -> ExtractionService:
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = get_extraction_service()
    return _extraction_service


def _get_validation() -> ValidationService:
    global _validation_service
    if _validation_service is None:
        _validation_service = get_validation_service()
    return _validation_service


def _get_scoring() -> ScoringService:
    global _scoring_service
    if _scoring_service is None:
        _scoring_service = get_scoring_service()
    return _scoring_service


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Health check."""
    db = get_db()
    return HealthResponse(
        status="ok",
        llm_configured=_get_extraction().llm_configured,
        database_connected=db.connected,
    )


@app.post("/extract", response_model=ParsedBill, tags=["extraction"])
def extract(req: ExtractRequest) -> ParsedBill:
    """Extract a draft ParsedBill from raw OCR text + layout JSON."""
    if not req.raw_ocr_text.strip():
        raise HTTPException(status_code=400, detail="raw_ocr_text must not be empty")

    service = _get_extraction()
    request = ExtractionRequest(
        raw_ocr_text=req.raw_ocr_text,
        layout_json=req.layout_json,
        document_id=req.document_id,
    )
    try:
        draft = service.extract(request)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Extraction failed")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")

    return draft


@app.post("/validate", response_model=ParsedBill, tags=["validation"])
def validate(req: ValidateRequest) -> ParsedBill:
    """Validate a draft ParsedBill, setting verified flags and warnings."""
    service = _get_validation()
    try:
        validated = service.validate(req.parsed_bill)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Validation failed")
        raise HTTPException(status_code=500, detail=f"Validation failed: {exc}")

    # Persist validated result to PostgreSQL (if configured)
    db = get_db()
    if db.connected:
        db.save_parsed_bill(validated)

    return validated


@app.post("/score", response_model=ParsedBill, tags=["scoring"])
def score(req: ScoreRequest) -> ParsedBill:
    """Score a validated ParsedBill, adding pricing-anomaly and appeal-success
    fields with SHAP explanations."""
    service = _get_scoring()
    try:
        scored = service.score(req.parsed_bill)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Scoring failed")
        raise HTTPException(status_code=500, detail=f"Scoring failed: {exc}")

    # Persist scored result to PostgreSQL (if configured)
    db = get_db()
    if db.connected:
        db.save_parsed_bill(scored)

    return scored


# ---------------------------------------------------------------------------
# Convenience: full pipeline endpoint (optional, for testing/demo)
# ---------------------------------------------------------------------------
class FullPipelineRequest(BaseModel):
    raw_ocr_text: str
    layout_json: Optional[Dict[str, Any]] = None
    document_id: Optional[str] = None


@app.post("/pipeline", response_model=ParsedBill, tags=["pipeline"])
def full_pipeline(req: FullPipelineRequest) -> ParsedBill:
    """Run extract → validate → score in one call. Useful for demos/tests.

    On recoverable internal failures, returns a best-effort structured bill
    with warnings in audit. On total failure, returns HTTP 500 with a clear error.
    """
    if not req.raw_ocr_text.strip():
        raise HTTPException(status_code=400, detail="raw_ocr_text must not be empty")

    document_id = req.document_id or f"doc-{uuid.uuid4().hex[:12]}"

    # 1. Extract
    try:
        draft = _get_extraction().extract(
            ExtractionRequest(
                raw_ocr_text=req.raw_ocr_text,
                layout_json=req.layout_json,
                document_id=document_id,
            )
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Pipeline extraction failed")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")

    # 2. Validate
    try:
        validated = _get_validation().validate(draft)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Pipeline validation failed")
        # Best-effort: return the draft with a warning in audit
        draft.audit["pipeline_error"] = f"Validation failed: {exc}"
        draft.audit["extraction_engine"] = "member2-v1"
        draft.status = DocumentStatus.error
        return draft

    # 3. Score
    try:
        scored = _get_scoring().score(validated)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Pipeline scoring failed")
        # Best-effort: return the validated bill with a warning in audit
        validated.audit["pipeline_error"] = f"Scoring failed: {exc}"
        validated.audit["extraction_engine"] = "member2-v1"
        validated.status = DocumentStatus.analyzed
        return validated

    # Mark as analyzed per the backend contract
    scored.status = DocumentStatus.analyzed
    scored.audit["extraction_engine"] = "member2-v1"

    db = get_db()
    if db.connected:
        db.save_parsed_bill(scored)

    return scored
