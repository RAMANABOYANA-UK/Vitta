"""
Client for Member 2's Data Extraction + XGBoost Scoring service.

This is the only place in the backend that knows how to talk to Member 2.
The rest of the system just calls `extract_and_score()`.

Design principles:
- Optional: controlled by EXTRACTION_SERVICE_ENABLED
- Never raises in development: always returns a usable ParsedBill
- Strict mode (EXTRACTION_STRICT_MODE=true): raises on failure so the
  caller can surface a structured error instead of silently using mock data
- Preserves extra fields that Member 2 may return
- Clear logging: which path was used, timings, failures
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings
from app.schemas import ParsedBill
from app.services.mock_data import generate_mock_parsed_bill

logger = logging.getLogger(__name__)


class ExtractionServiceError(Exception):
    """Raised when extraction fails in strict mode."""


async def extract_and_score(
    document_id: str,
    original_filename: str,
    raw_ocr_text: Optional[str] = None,
) -> ParsedBill:
    """
    Obtain a structured + scored ParsedBill.

    Path selection:
    1. If EXTRACTION_SERVICE_ENABLED=False → mock
    2. If Member 2 is unreachable / times out / returns error:
       - strict mode → raise ExtractionServiceError
       - dev mode → fall back to mock
    3. On success → return Member 2's ParsedBill
    """
    if not settings.EXTRACTION_SERVICE_ENABLED:
        logger.info(
            "Extraction service disabled — using mock | document_id=%s",
            document_id,
        )
        return _mock(document_id, original_filename)

    url = f"{settings.EXTRACTION_SERVICE_URL.rstrip('/')}/pipeline"

    # Use real extracted text when available; otherwise a clear placeholder
    payload_text = raw_ocr_text or f"[No text extracted for {original_filename}]"
    payload = {
        "document_id": document_id,
        "raw_ocr_text": payload_text,
    }

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=settings.EXTRACTION_SERVICE_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

            data = response.json()
            bill = ParsedBill.model_validate(data)

            elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

            # Light observability
            n_flags = sum(len(item.flags) for item in bill.line_items)
            appeal_prob = None
            if bill.appeal_prediction:
                appeal_prob = getattr(bill.appeal_prediction, "success_probability", None)

            logger.info(
                "Member 2 extraction+scoring succeeded | document_id=%s | "
                "path=member2 | elapsed_ms=%.1f | flags=%d | appeal_prob=%s | "
                "text_chars=%d",
                document_id,
                elapsed_ms,
                n_flags,
                appeal_prob,
                len(payload_text),
            )
            return bill

    except httpx.TimeoutException:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        msg = (
            f"Extraction service timed out after {settings.EXTRACTION_SERVICE_TIMEOUT_SECONDS}s "
            f"| document_id={document_id} | elapsed_ms={elapsed_ms}"
        )
        logger.warning(msg)
        return _handle_failure(document_id, original_filename, msg)

    except httpx.ConnectError:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        msg = (
            f"Extraction service unreachable at {settings.EXTRACTION_SERVICE_URL} "
            f"| document_id={document_id} | elapsed_ms={elapsed_ms}"
        )
        logger.warning(msg)
        return _handle_failure(document_id, original_filename, msg)

    except httpx.HTTPStatusError as e:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        msg = (
            f"Extraction service returned HTTP {e.response.status_code} "
            f"| document_id={document_id} | elapsed_ms={elapsed_ms} | "
            f"body={e.response.text[:300]}"
        )
        logger.error(msg)
        return _handle_failure(document_id, original_filename, msg)

    except Exception as e:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        msg = (
            f"Unexpected error calling extraction service | document_id={document_id} "
            f"| elapsed_ms={elapsed_ms} | error={str(e)}"
        )
        logger.exception(msg)
        return _handle_failure(document_id, original_filename, msg)


def _handle_failure(
    document_id: str, original_filename: str, error_message: str
) -> ParsedBill:
    """Handle an extraction failure based on strict mode."""
    if settings.EXTRACTION_STRICT_MODE:
        raise ExtractionServiceError(error_message)
    logger.warning(
        "Falling back to mock | document_id=%s | reason=%s",
        document_id,
        error_message,
    )
    return _mock(document_id, original_filename)


def _mock(document_id: str, original_filename: str) -> ParsedBill:
    """Centralized mock fallback."""
    return generate_mock_parsed_bill(
        document_id=document_id,
        original_filename=original_filename,
        uploaded_at=datetime.now(timezone.utc),
    )