"""
Document processing pipeline.

Clean staged composition:
1. Extraction + XGBoost scoring (Member 2 or mock)
2. Deterministic Rust rules engine
3. Grounded letter generation + verification
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict

from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.models import Document
from app.schemas import DocumentStatus, ParsedBill
from app.services.extraction_client import extract_and_score
from app.services.letter_generator import generate_appeal_letter
from app.services.rules_engine import apply_rules

logger = logging.getLogger(__name__)

# Status transition validation map
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    DocumentStatus.uploaded.value: {DocumentStatus.processing.value, DocumentStatus.error.value},
    DocumentStatus.processing.value: {
        DocumentStatus.analyzed.value,
        DocumentStatus.letter_ready.value,
        DocumentStatus.error.value,
    },
    DocumentStatus.analyzed.value: {DocumentStatus.letter_ready.value, DocumentStatus.error.value},
    DocumentStatus.letter_ready.value: set(),
    DocumentStatus.error.value: set(),
}


def validate_transition(current: str, new: str) -> bool:
    return new in _ALLOWED_TRANSITIONS.get(current, set())


async def update_document_status(
    session: AsyncSession,
    document: Document,
    new_status: str,
    error_message: str | None = None,
) -> Document:
    if not validate_transition(document.status, new_status):
        logger.warning(
            "Invalid status transition for %s: %s -> %s",
            document.id,
            document.status,
            new_status,
        )
        raise ValueError(f"Invalid status transition: {document.status} -> {new_status}")

    document.status = new_status
    document.error_message = error_message
    session.add(document)
    await session.commit()
    await session.refresh(document)
    logger.info("Document %s status -> %s", document.id, new_status)
    return document


def _init_audit() -> Dict[str, Any]:
    """Create a fresh audit dictionary."""
    return {
        "pipeline_version": "0.3.0",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "extraction_path": None,
        "rules_engine": {
            "enabled": settings.RULES_ENGINE_ENABLED,
            "flags_added": 0,
            "status": "skipped",
        },
        "scoring": {
            "anomaly_flags": 0,
            "appeal_probability": None,
            "model_version": None,
        },
        "letter": {
            "status": None,
            "verified_fields_count": 0,
            "verification_passed": None,
            "problems": [],
        },
        "timings_ms": {},
        "completed_at": None,
    }


async def run_pipeline(
    document_id: str,
    original_filename: str,
    raw_ocr_text: str | None = None,
) -> ParsedBill:
    """
    Fully observable pipeline.
    Every stage records timing, path taken, and key metrics into the audit object.
    """
    logger.info("Pipeline started | document_id=%s", document_id)
    audit = _init_audit()
    t0 = time.perf_counter()

    # Optional demo delay
    if settings.PIPELINE_DELAY_SECONDS > 0:
        await asyncio.sleep(settings.PIPELINE_DELAY_SECONDS)

    # ------------------------------------------------------------------
    # Stage 1: Extraction + XGBoost scoring
    # ------------------------------------------------------------------
    t_stage = time.perf_counter()
    result = await extract_and_score(
        document_id=document_id,
        original_filename=original_filename,
        raw_ocr_text=raw_ocr_text,
    )
    audit["timings_ms"]["extraction"] = round((time.perf_counter() - t_stage) * 1000, 1)

    # Determine which path was used
    if settings.EXTRACTION_SERVICE_ENABLED:
        audit["extraction_path"] = "member2"
    else:
        audit["extraction_path"] = "mock"

    # Capture scoring signals if present
    anomaly_count = 0
    for item in result.line_items:
        for flag in item.flags:
            if flag.type in ("pricing_anomaly", "anomaly", "price_anomaly"):
                anomaly_count += 1
    audit["scoring"]["anomaly_flags"] = anomaly_count

    if result.appeal_prediction:
        audit["scoring"]["appeal_probability"] = getattr(
            result.appeal_prediction, "success_probability", None
        )
        audit["scoring"]["model_version"] = getattr(
            result.appeal_prediction, "model_version", None
        )

    logger.info(
        "Stage extraction completed | document_id=%s | path=%s | anomaly_flags=%d | appeal_prob=%s",
        document_id,
        audit["extraction_path"],
        anomaly_count,
        audit["scoring"]["appeal_probability"],
    )

    # ------------------------------------------------------------------
    # Stage 2: Deterministic Rust rules
    # ------------------------------------------------------------------
    t_stage = time.perf_counter()
    flags_before = sum(len(i.flags) for i in result.line_items)
    result = await apply_rules(result)
    flags_after = sum(len(i.flags) for i in result.line_items)
    flags_added = max(0, flags_after - flags_before)

    audit["timings_ms"]["rules"] = round((time.perf_counter() - t_stage) * 1000, 1)
    audit["rules_engine"]["flags_added"] = flags_added
    audit["rules_engine"]["status"] = "applied" if settings.RULES_ENGINE_ENABLED else "disabled"

    logger.info(
        "Stage rules completed | document_id=%s | flags_added=%d | total_flags=%d",
        document_id,
        flags_added,
        flags_after,
    )

    # ------------------------------------------------------------------
    # Stage 3: Grounded letter + verification
    # ------------------------------------------------------------------
    t_stage = time.perf_counter()
    result.letter = await generate_appeal_letter(result)
    audit["timings_ms"]["letter"] = round((time.perf_counter() - t_stage) * 1000, 1)

    if result.letter:
        audit["letter"]["status"] = result.letter.status
        verified = result.letter.verified_fields or []
        audit["letter"]["verified_fields_count"] = len(verified)
        # Authoritative pass/fail comes from the verifier (zero problems), not
        # from the count of verified fields. A letter can carry verified fields
        # AND unresolved problems simultaneously, so `len(verified) > 0` would
        # wrongly report a partially-verified letter as passed.
        audit["letter"]["verification_passed"] = result.letter.verification_passed
        audit["letter"]["problems"] = list(result.letter.problems or [])

    logger.info(
        "Stage letter completed | document_id=%s | letter_status=%s | verified_fields=%d",
        document_id,
        audit["letter"]["status"],
        audit["letter"]["verified_fields_count"],
    )

    # ------------------------------------------------------------------
    # Finalize audit
    # ------------------------------------------------------------------
    audit["completed_at"] = datetime.now(timezone.utc).isoformat()
    audit["timings_ms"]["total"] = round((time.perf_counter() - t0) * 1000, 1)

    # Attach audit to the result
    result.audit = audit

    logger.info(
        "Pipeline completed | document_id=%s | total_ms=%.1f | extraction=%s | rules_flags=%d | letter=%s",
        document_id,
        audit["timings_ms"]["total"],
        audit["extraction_path"],
        flags_added,
        audit["letter"]["status"],
    )
    return result
