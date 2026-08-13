"""
Document upload, retrieval, and status endpoints.
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import generate_storage_key
from app.database import get_session
from app.models import Document
from app.schemas import (
    DocumentDetailResponse,
    DocumentResponse,
    DocumentStatus,
    DocumentStatusResponse,
    Letter,
    LetterUpdateRequest,
    ParsedBill,
)
from app.services.letter_verifier import verify_letter
from app.services.pipeline import run_pipeline, update_document_status
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# Maximum upload size: 25 MB
MAX_UPLOAD_SIZE = 25 * 1024 * 1024

# Allowed content types for medical bills
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}


async def _get_document_or_404(
    document_id: str, session: AsyncSession
) -> Document:
    """Fetch a document by ID or raise 404."""
    document = await session.get(Document, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    return document


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a medical bill document",
)
async def upload_document(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> Document:
    """
    Upload a medical bill document (PDF, image) to storage and create a
    database record. Kicks off the analysis pipeline in the background.
    """
    # Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{file.content_type}'. "
                f"Allowed types: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
            ),
        )

    # Validate size
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_UPLOAD_SIZE // (1024 * 1024)} MB limit",
        )

    # Generate storage key and persist
    storage_key = generate_storage_key(file.filename or "upload.pdf")
    try:
        await storage_service.save(
            storage_key, contents, file.content_type or "application/pdf"
        )
    except Exception as e:
        logger.exception("Storage failure for upload %s", storage_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store file: {str(e)}",
        )

    # Create DB record
    document = Document(
        original_filename=file.filename or "upload.pdf",
        storage_key=storage_key,
        content_type=file.content_type or "application/pdf",
        status=DocumentStatus.uploaded.value,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    logger.info("Document created: %s (%s)", document.id, document.original_filename)

    # Kick off the analysis pipeline in the background
    asyncio.create_task(
        _process_document_background(document.id, document.original_filename)
    )

    return document


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Get a document and its analysis result",
)
async def get_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Retrieve a document by ID, including the parsed bill result if available."""
    document = await _get_document_or_404(document_id, session)

    # Parse result_json into a ParsedBill if present
    result = None
    if document.result_json:
        try:
            result = ParsedBill.model_validate(document.result_json)
        except Exception:
            logger.warning(
                "Document %s has invalid result_json; returning raw data",
                document_id,
            )
            result = document.result_json  # type: ignore[assignment]

    return {
        "id": document.id,
        "original_filename": document.original_filename,
        "storage_key": document.storage_key,
        "content_type": document.content_type,
        "status": document.status,
        "error_message": document.error_message,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "result": result,
    }


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="Get a document's processing status",
)
async def get_document_status(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Check the current processing status of a document."""
    document = await _get_document_or_404(document_id, session)
    return {
        "id": document.id,
        "status": document.status,
        "error_message": document.error_message,
        "updated_at": document.updated_at,
    }


@router.patch(
    "/{document_id}/letter",
    summary="Update and verify a document's appeal letter",
)
async def update_letter(
    document_id: str,
    body: LetterUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Allow editing a letter and re-verifying it against the bill."""
    document = await _get_document_or_404(document_id, session)
    if not document.result_json:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has not finished processing yet",
        )

    bill = ParsedBill.model_validate(document.result_json)
    is_valid, verified_fields, problems = verify_letter(bill, body.content_markdown)

    bill.letter = Letter(
        status="edited",
        content_markdown=body.content_markdown,
        verified_fields=verified_fields,
    )

    document.result_json = bill.model_dump(mode="json")
    session.add(document)
    await session.commit()

    return {
        "document_id": document_id,
        "letter": bill.letter,
        "is_fully_verified": is_valid,
        "problems": problems,
    }


async def _process_document_background(
    document_id: str, original_filename: str
) -> None:
    """
    Reliable background pipeline.

    Guarantees the document always ends in a terminal state:
    `letter_ready` or `error` — never stuck in `processing`.

    Order of operations on success:
      1. uploaded → processing
      2. Run the full pipeline (mock extraction → rules → letter)
      3. Persist `result_json` FIRST (separate commit)
      4. Then move to `letter_ready` (separate commit)

    This two-phase commit ensures that even if the status update fails,
    the result is already durable and the document can be recovered.
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        document = await session.get(Document, document_id)
        if not document:
            logger.error("Background pipeline: document %s not found", document_id)
            return

        try:
            # uploaded → processing
            await update_document_status(
                session, document, DocumentStatus.processing.value
            )

            # Run full pipeline (mock extraction → rules → letter)
            result = await run_pipeline(document_id, original_filename)

            # Persist result FIRST, then move to terminal status.
            # Two separate commits so a failure in the status transition
            # never loses the computed result.
            document.result_json = result.model_dump(mode="json")
            session.add(document)
            await session.commit()
            await session.refresh(document)

            await update_document_status(
                session, document, DocumentStatus.letter_ready.value
            )

            logger.info("Pipeline succeeded for document %s", document_id)

        except Exception as e:
            logger.exception("Pipeline failed for document %s", document_id)
            try:
                doc = await session.get(Document, document_id)
                if doc:
                    doc.status = DocumentStatus.error.value
                    doc.error_message = str(e)[:1000]
                    session.add(doc)
                    await session.commit()
            except Exception:
                logger.exception(
                    "Failed to mark document %s as error", document_id
                )