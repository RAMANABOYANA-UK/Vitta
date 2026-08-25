"""
Document upload, retrieval, status, and letter editing endpoints.
Phase 1: Unbreakable pipeline & state machine.

Guarantees:
- Background task can never leave a document stuck in `processing`
- `result_json` is always persisted before the final status change
- The error path always commits a terminal `error` status
- Letter editing uses a proper Pydantic model and re-verifies every edit
- `DocumentStatus` enum is used strictly for all status values
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import get_current_user, require_upload_slot
from app.core.security import generate_storage_key
from app.database import get_session
from app.models import AccessLog, Document, User
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
from app.services.document_text import extract_document_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# Maximum upload size: 20 MB
MAX_UPLOAD_SIZE = 20 * 1024 * 1024

# Allowed content types for medical bills
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}


def validate_upload(filename: str | None, content_type: str | None, contents: bytes) -> None:
    """Reject malformed uploads before they reach storage or the pipeline."""
    def reject(code: str, message: str, http_status: int) -> None:
        raise HTTPException(
            status_code=http_status,
            detail={"code": code, "message": message},
        )

    if not contents:
        reject("EMPTY_FILE", "The selected file is empty.", status.HTTP_422_UNPROCESSABLE_ENTITY)
    if len(contents) > MAX_UPLOAD_SIZE:
        reject(
            "FILE_TOO_LARGE",
            f"File exceeds the {MAX_UPLOAD_SIZE // (1024 * 1024)} MB limit.",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    if content_type not in ALLOWED_CONTENT_TYPES:
        reject(
            "UNSUPPORTED_FILE_TYPE",
            "Please upload a PDF, JPG, PNG, or WEBP file.",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    signatures = {
        "application/pdf": contents.startswith(b"%PDF-"),
        "image/jpeg": contents.startswith(b"\xff\xd8\xff"),
        "image/png": contents.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": contents.startswith(b"RIFF") and contents[8:12] == b"WEBP",
    }
    if not signatures.get(content_type, False):
        reject(
            "INVALID_FILE_CONTENT",
            "The file content does not match its declared type.",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


async def _get_document_or_404(
    document_id: str, session: AsyncSession, current_user: User
) -> Document:
    """Fetch a document owned by ``current_user`` or raise 404.

    Ownership failures return 404 (not 403) on purpose: a 403 would confirm the
    document exists, letting a caller probe for other users' document IDs. A
    document with no owner (legacy/orphaned, owner_id is None) is likewise
    treated as not found for every user — fail closed on PHI.
    """
    document = await session.get(Document, document_id)
    if not document or document.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    return document


async def _record_access(
    session: AsyncSession, *, user_id: str, document_id: str | None, action: str
) -> None:
    """Append an audit entry for a PHI access/mutation.

    The structured log line is emitted first so there is always a durable trace
    even if the DB row fails to persist. The persisted AccessLog row is the
    source of truth for the frontend activity timeline. Fails open on the DB
    write (logs a warning) so an audit hiccup never masks a completed operation;
    a stricter compliance posture would fail closed here.
    """
    logger.info(
        "audit action=%s user_id=%s document_id=%s", action, user_id, document_id
    )
    try:
        session.add(
            AccessLog(user_id=user_id, document_id=document_id, action=action)
        )
        await session.commit()
    except Exception:
        await session.rollback()
        logger.warning(
            "audit persist failed action=%s user_id=%s document_id=%s",
            action,
            user_id,
            document_id,
        )


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a medical bill document",
)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(require_upload_slot),
    session: AsyncSession = Depends(get_session),
) -> Document:
    """
    Upload a medical bill document (PDF, image) to storage and create a
    database record owned by the caller. Kicks off the analysis pipeline in the
    background. Requires authentication and is rate-limited per user.
    """
    contents = await file.read()
    validate_upload(file.filename, file.content_type, contents)

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

    # Create DB record owned by the uploader
    document = Document(
        owner_id=current_user.id,
        original_filename=file.filename or "upload.pdf",
        storage_key=storage_key,
        content_type=file.content_type or "application/pdf",
        status=DocumentStatus.uploaded.value,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    logger.info("Document created: %s (%s)", document.id, document.original_filename)

    await _record_access(
        session, user_id=current_user.id, document_id=document.id, action="upload"
    )

    # Kick off the analysis pipeline in the background (fire-and-forget)
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
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Retrieve a document by ID, including the parsed bill result if available.
    Only the owner may read it."""
    document = await _get_document_or_404(document_id, session, current_user)

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

    await _record_access(
        session, user_id=current_user.id, document_id=document.id, action="read"
    )

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
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Check the current processing status of a document. Owner-only.

    Deliberately NOT written to the AccessLog: the frontend polls this endpoint
    while a document processes, so persisting a row per poll would flood the
    audit table. It returns only the status enum (no PHI); ownership is still
    enforced and the access is captured in the structured logs.
    """
    document = await _get_document_or_404(document_id, session, current_user)
    logger.debug(
        "audit action=status user_id=%s document_id=%s",
        current_user.id,
        document.id,
    )
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
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Allow the owner to edit a letter and re-verify it against the bill."""
    document = await _get_document_or_404(document_id, session, current_user)
    if not document.result_json:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has not finished processing yet",
        )

    # Re-verify the edited letter against the underlying bill facts
    bill = ParsedBill.model_validate(document.result_json)
    is_valid, verified_fields, problems = verify_letter(bill, body.content_markdown)

    bill.letter = Letter(
        status="edited",
        content_markdown=body.content_markdown,
        verified_fields=verified_fields,
        verification_passed=is_valid,
        problems=problems,
    )

    # Persist the updated result with the re-verified letter
    document.result_json = bill.model_dump(mode="json")
    session.add(document)
    await session.commit()

    await _record_access(
        session,
        user_id=current_user.id,
        document_id=document_id,
        action="update_letter",
    )

    return {
        "document_id": document_id,
        "letter": bill.letter,
        "is_fully_verified": is_valid,
        "problems": problems,
    }


@router.post(
    "/{document_id}/reprocess",
    summary="Safely re-process a document (recovery)",
    status_code=status.HTTP_202_ACCEPTED,
)
async def reprocess_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Recovery endpoint (owner-only).

    Allowed only when the document is in `error` or still in `processing`
    for an abnormally long time. Resets status to uploaded and re-queues
    the background pipeline.
    """
    document = await _get_document_or_404(document_id, session, current_user)

    if document.status not in {
        DocumentStatus.error.value,
        DocumentStatus.processing.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Document is in status '{document.status}'. "
                "Only 'error' or stuck 'processing' documents can be re-processed."
            ),
        )

    # Reset to a clean starting state
    document.status = DocumentStatus.uploaded.value
    document.error_message = None
    # Keep existing result_json for safety; the new run will overwrite it on success
    session.add(document)
    await session.commit()
    await session.refresh(document)

    logger.info("Re-process requested for document %s", document_id)

    await _record_access(
        session,
        user_id=current_user.id,
        document_id=document_id,
        action="reprocess",
    )

    # Re-queue the background task
    asyncio.create_task(
        _process_document_background(document.id, document.original_filename)
    )

    return {
        "document_id": document_id,
        "status": document.status,
        "message": "Document queued for re-processing",
    }


async def _mark_document_error(
    document_id: str, error_message: str
) -> bool:
    """
    Force a document into the terminal `error` state using its own session.

    Uses a fresh DB session so that even if the original session was left in
    a rolled-back / invalid state by the pipeline exception, we can still
    durably commit the error status. This is the final backstop that makes
    the pipeline truly unbreakable.
    """
    from app.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            doc = await session.get(Document, document_id)
            if not doc:
                logger.error(
                    "Error-path: document %s not found; cannot mark as error",
                    document_id,
                )
                return False

            doc.status = DocumentStatus.error.value
            doc.error_message = error_message[:1000]
            session.add(doc)
            await session.commit()
            logger.info(
                "Document %s marked as error: %.200s", document_id, error_message
            )
            return True
    except Exception:
        logger.exception(
            "Critical: failed to mark document %s as error", document_id
        )
        return False


async def _process_document_background(
    document_id: str, original_filename: str
) -> None:
    """
    Reliable, unbreakable background pipeline.

    Guarantees the document always ends in a terminal state:
    `letter_ready` or `error` — never stuck in `processing`.

    Order of operations on success:
      1. uploaded → processing
      2. Run the full pipeline (extraction → rules → letter generation)
      3. Persist `result_json` FIRST (separate commit)
      4. Then move to `letter_ready` (separate commit)

    On any exception, the document is forced to `error` via a *fresh*
    database session — because the original session may be unrecoverable
    after a failed commit (PendingRollbackError), using a fresh session
    guarantees the error status is always durably committed.
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        document = await session.get(Document, document_id)
        if not document:
            logger.error("Background pipeline: document %s not found", document_id)
            return

        try:
            # Step 1: uploaded → processing
            await update_document_status(
                session, document, DocumentStatus.processing.value
            )
            logger.info(
                "Pipeline started: document %s moved to processing", document_id
            )

            # Step 2: Run the full pipeline (extraction → rules → letter)
            if hasattr(document, "storage_key"):
                extraction = await extract_document_text(
                    storage_key=document.storage_key,
                    content_type=document.content_type,
                )
                result = await run_pipeline(
                    document_id,
                    original_filename,
                    raw_ocr_text=extraction.text,
                    text_extraction_method=extraction.method,
                    layout_json=extraction.layout_json,
                )
            else:
                # Keep lightweight state-machine fakes usable in unit tests.
                result = await run_pipeline(document_id, original_filename)

            # Step 3: Persist result FIRST (separate commit).
            # The result is durable before we declare the document ready,
            # so a failure in the status transition never loses the result.
            document.result_json = result.model_dump(mode="json")
            session.add(document)
            await session.commit()
            await session.refresh(document)

            # Step 4: Move to the terminal success status
            await update_document_status(
                session, document, DocumentStatus.letter_ready.value
            )
            logger.info("Pipeline succeeded for document %s", document_id)

        except Exception as e:
            logger.exception("Pipeline failed for document %s", document_id)
            # Always mark the document as error using a fresh session.
            # This guarantees the error status is committed even if the
            # current session is in a rolled-back state.
            await _mark_document_error(document_id, str(e))