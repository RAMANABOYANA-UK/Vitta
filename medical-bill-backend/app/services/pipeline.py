"""
Document processing pipeline.

Phase 1 uses a mock pipeline that simulates the full analysis flow:
  uploaded → processing → analyzed → letter_ready

The pipeline is designed with clear extension points so that later phases can
swap in the real extraction engine, Rust rules engine, and LLM letter generator
without changing the API or orchestration contract.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.models import Document
from app.services.letter_generator import generate_appeal_letter
from app.services.mock_data import generate_mock_parsed_bill
from app.services.rules_engine import apply_rules
from app.schemas import DocumentStatus, ParsedBill

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
    """Validate that a status transition is allowed."""
    return new in _ALLOWED_TRANSITIONS.get(current, set())


async def update_document_status(
    session: AsyncSession,
    document: Document,
    new_status: str,
    error_message: str | None = None,
) -> Document:
    """Update a document's status with transition validation."""
    if not validate_transition(document.status, new_status):
        logger.warning(
            "Invalid status transition for %s: %s -> %s",
            document.id,
            document.status,
            new_status,
        )
        raise ValueError(
            f"Invalid status transition: {document.status} -> {new_status}"
        )

    document.status = new_status
    document.error_message = error_message
    session.add(document)
    await session.commit()
    await session.refresh(document)
    logger.info("Document %s status -> %s", document.id, new_status)
    return document


async def run_pipeline(document_id: str, original_filename: str) -> ParsedBill:
    """
    Run the (mock) analysis pipeline for a document.

    This function performs the simulated work and returns the final ParsedBill.
    The document status transitions are handled by the caller (the upload route
    that spawned this task) to keep the pipeline pure and easily testable.

    Extension points:
      - Replace the mock generator with the real OCR/extraction engine.
      - Invoke the Rust rules engine before building the prediction.
      - Use a real LLM for the appeal letter.
    """
    logger.info("Pipeline started for document %s", document_id)

    # Simulate extraction + rules engine + letter generation work
    await asyncio.sleep(settings.PIPELINE_DELAY_SECONDS)

    if settings.MOCK_PIPELINE:
        result = generate_mock_parsed_bill(
            document_id=document_id,
            original_filename=original_filename,
            uploaded_at=datetime.now(timezone.utc),
        )
    else:
        # Real pipeline placeholder — this is where the actual extraction
        # service would be invoked in a later phase.
        raise NotImplementedError(
            "Real extraction pipeline not yet implemented. "
            "Set MOCK_PIPELINE=true to use the mock pipeline."
        )

    # Apply deterministic rules from the Rust engine
    result = await apply_rules(result)

    # Generate a grounded + verified appeal letter
    result.letter = await generate_appeal_letter(result)

    logger.info(
        "Pipeline completed for document %s: %d line items, %d denials, %d flags",
        document_id,
        len(result.line_items),
        len(result.denial_codes),
        sum(len(i.flags) for i in result.line_items),
    )
    return result