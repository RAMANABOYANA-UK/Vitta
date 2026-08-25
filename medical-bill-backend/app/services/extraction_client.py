"""
Client for Member 2's Data Extraction + XGBoost Scoring service.

This is the only place in the backend that knows how to talk to Member 2.
The rest of the system just calls `extract_and_score()`.

Design principles:
- Optional: controlled by EXTRACTION_SERVICE_ENABLED
- Never raises: always returns a usable ParsedBill
- Graceful fallback to mock on any failure
- Preserves extra fields that Member 2 may return
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings
from app.schemas import ParsedBill
from app.services.mock_data import generate_mock_parsed_bill

logger = logging.getLogger(__name__)


async def extract_and_score(
    document_id: str,
    original_filename: str,
    raw_ocr_text: Optional[str] = None,
) -> ParsedBill:
    """
    Obtain a structured + scored ParsedBill.

    Path selection:
    1. If EXTRACTION_SERVICE_ENABLED=False → mock
    2. If Member 2 is unreachable / times out / returns error → mock
    3. On success → return Member 2's ParsedBill
    """
    if not settings.EXTRACTION_SERVICE_ENABLED:
        logger.info(
            "Extraction service disabled — using mock | document_id=%s", document_id
        )
        return _mock(document_id, original_filename)

    url = f"{settings.EXTRACTION_SERVICE_URL.rstrip('/')}/pipeline"

    payload = {
        "document_id": document_id,
        "raw_ocr_text": raw_ocr_text or "",
    }

    if not payload["raw_ocr_text"]:
        logger.error(
            "No extracted document text available | document_id=%s",
            document_id,
        )
        return _mock(document_id, original_filename)

    try:
        async with httpx.AsyncClient(
            timeout=settings.EXTRACTION_SERVICE_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

            data = response.json()
            bill = ParsedBill.model_validate(data)

            # Light observability
            n_flags = sum(len(item.flags) for item in bill.line_items)
            appeal_prob = None
            if bill.appeal_prediction:
                appeal_prob = getattr(bill.appeal_prediction, "success_probability", None)

            logger.info(
                "Member 2 extraction+scoring succeeded | document_id=%s | flags=%d | appeal_prob=%s",
                document_id,
                n_flags,
                appeal_prob,
            )
            return bill

    except httpx.TimeoutException:
        logger.warning(
            "Extraction service timed out after %.1fs — falling back to mock | document_id=%s",
            settings.EXTRACTION_SERVICE_TIMEOUT_SECONDS,
            document_id,
        )
        return _mock(document_id, original_filename)

    except httpx.ConnectError:
        logger.warning(
            "Extraction service unreachable at %s — falling back to mock | document_id=%s",
            settings.EXTRACTION_SERVICE_URL,
            document_id,
        )
        return _mock(document_id, original_filename)

    except httpx.HTTPStatusError as e:
        logger.error(
            "Extraction service returned HTTP %s — falling back to mock | document_id=%s | body=%s",
            e.response.status_code,
            document_id,
            e.response.text[:300],
        )
        return _mock(document_id, original_filename)

    except Exception as e:
        logger.exception(
            "Unexpected error calling extraction service — falling back to mock | document_id=%s | error=%s",
            document_id,
            str(e),
        )
        return _mock(document_id, original_filename)


def _mock(document_id: str, original_filename: str) -> ParsedBill:
    """Centralized mock fallback."""
    return generate_mock_parsed_bill(
        document_id=document_id,
        original_filename=original_filename,
        uploaded_at=datetime.now(timezone.utc),
    )