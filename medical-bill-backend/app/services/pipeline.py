"""
Document processing pipeline.

Clean staged composition:
1. Extraction + XGBoost scoring (Member 2 or mock)
2. Deterministic Rust rules engine
3. Grounded letter generation + verification
"""

import asyncio
import logging

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


async def run_pipeline(document_id: str, original_filename: str) -> ParsedBill:
    """
    Pure pipeline composition.

    Stages:
    1. Extraction + XGBoost scoring (Member 2 or mock)
    2. Rust deterministic rules
    3. Grounded letter generation + verification
    """
    logger.info("Pipeline started for document %s", document_id)

    # Optional artificial delay for demo realism
    if settings.PIPELINE_DELAY_SECONDS > 0:
        await asyncio.sleep(settings.PIPELINE_DELAY_SECONDS)

    # Stage 1: Extraction + scoring
    result = await extract_and_score(
        document_id=document_id,
        original_filename=original_filename,
    )

    # Stage 2: Deterministic rules (Rust)
    result = await apply_rules(result)

    # Stage 3: Grounded letter + verification
    result.letter = await generate_appeal_letter(result)

    total_flags = sum(len(item.flags) for item in result.line_items)
    logger.info(
        "Pipeline completed | document_id=%s | line_items=%d | flags=%d | letter_status=%s",
        document_id,
        len(result.line_items),
        total_flags,
        result.letter.status if result.letter else None,
    )
    return result