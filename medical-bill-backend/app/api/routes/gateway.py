"""
Frontend gateway router.

The browser app (js/api.js) was built against a resource-oriented contract
(``/upload``, ``/jobs/{id}/status``, ``/bills/{id}``, ``/bills/{id}/flags``,
``/bills/{id}/appeal-score``) whose field names and shapes differ from the
backend's ParsedBill. This router is an ADDITIVE adapter layer: it serves the
frontend's exact shapes on top of the existing pipeline, reusing the document
routes' auth, owner-scoping, audit-logging, and background-processing helpers.

It does NOT replace ``/api/v1/documents/*`` — those remain the canonical,
backend-native API. This gateway simply lets the existing frontend talk to the
real backend without a rewrite. All translation lives in
``app.services.frontend_adapter`` (pure, unit-tested); this module only wires
HTTP + persistence around it.

Endpoints (all under ``/api/v1``, matching the HttpClientVittaAPI call sites):
    POST   /upload                               -> {documentId, jobId, ...}
    GET    /jobs/{job_id}/status                  -> PipelineStatus
    GET    /bills/{document_id}                   -> ParsedBill (frontend shape)
    GET    /bills/{document_id}/flags             -> FlagSet
    GET    /bills/{document_id}/appeal-score      -> AppealScore
    POST   /bills/{document_id}/appeal-score/recompute -> AppealScore
    PATCH  /bills/{document_id}/letter            -> {documentId, letter, ...}

Not served here on purpose:
    * ``/codes/*`` — the backend has no code glossary; the frontend resolves
      codes locally from its bundled CODE_REFERENCE (see js/api.js).
    * ``/auth/logout`` — already served by the auth router.
    * ``/ws/jobs/{id}`` — no WebSocket; the frontend polls /jobs/{id}/status.
"""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import get_current_user, require_upload_slot
from app.core.security import generate_storage_key
from app.database import get_session
from app.models import Document, User
from app.schemas import DocumentStatus, Letter, LetterUpdateRequest, ParsedBill
from app.services.frontend_adapter import (
    to_frontend_appeal_score,
    to_frontend_bill,
    to_frontend_flagset,
    to_pipeline_status,
)
from app.services.letter_verifier import verify_letter
from app.services.storage import storage_service

# Reuse the document routes' shared helpers/constants so behavior (validation,
# ownership 404, audit trail, unbreakable background pipeline) stays identical.
from app.api.routes.documents import (
    ALLOWED_CONTENT_TYPES,
    MAX_UPLOAD_SIZE,
    validate_upload,
    _get_document_or_404,
    _process_document_background,
    _record_access,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["frontend-gateway"])


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/upload", status_code=status.HTTP_201_CREATED, summary="Upload a bill (frontend gateway)")
async def gateway_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(require_upload_slot),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Frontend-shaped upload. Mirrors POST /api/v1/documents/upload but returns
    the ``{documentId, jobId}`` envelope the browser client expects. Reuses the
    same validation, storage, ownership, audit, and background pipeline."""
    contents = await file.read()
    validate_upload(file.filename, file.content_type, contents)

    storage_key = generate_storage_key(file.filename or "upload.pdf")
    try:
        await storage_service.save(
            storage_key, contents, file.content_type or "application/pdf"
        )
    except Exception as e:
        logger.exception("Storage failure for gateway upload %s", storage_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store file: {str(e)}",
        )

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
    logger.info("Gateway upload created document %s", document.id)

    await _record_access(
        session, user_id=current_user.id, document_id=document.id, action="upload"
    )

    asyncio.create_task(
        _process_document_background(document.id, document.original_filename)
    )

    # Backend has no separate job entity — the job id mirrors the document id.
    return {
        "documentId": document.id,
        "jobId": document.id,
        "status": "uploading",
        "filename": document.original_filename,
        "createdAt": document.created_at,
    }


# ---------------------------------------------------------------------------
# Job status (polled)
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/status", summary="Pipeline status for a job (frontend gateway)")
async def gateway_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Return the PipelineStatus for a job. The job id IS the document id.

    Deliberately NOT written to the AccessLog: the frontend polls this every
    second while a document processes, so a row per poll would flood the audit
    table (same rationale as GET /documents/{id}/status). Ownership is still
    enforced; the access is captured in the structured logs.
    """
    document = await _get_document_or_404(job_id, session, current_user)
    logger.debug(
        "audit action=job_status user_id=%s document_id=%s", current_user.id, document.id
    )
    return to_pipeline_status(
        document.id, document.status, document.error_message, document.result_json
    )


# ---------------------------------------------------------------------------
# Bill / flags / appeal score
# ---------------------------------------------------------------------------


async def _require_processed(document: Document) -> Dict[str, Any]:
    """Return the stored result_json or raise 409 if processing has not finished.

    This backend persists result_json only at the end of the pipeline (just
    before letter_ready), so an absent result means "still processing".
    """
    if not document.result_json:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has not finished processing yet",
        )
    return document.result_json


@router.get("/bills/{document_id}", summary="Parsed bill (frontend shape)")
async def gateway_get_bill(
    document_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    document = await _get_document_or_404(document_id, session, current_user)
    result = await _require_processed(document)
    await _record_access(
        session, user_id=current_user.id, document_id=document.id, action="read"
    )
    return to_frontend_bill(result, document.id)


@router.get("/bills/{document_id}/flags", summary="Flag set (frontend shape)")
async def gateway_get_flags(
    document_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    document = await _get_document_or_404(document_id, session, current_user)
    result = await _require_processed(document)
    await _record_access(
        session, user_id=current_user.id, document_id=document.id, action="read_flags"
    )
    return to_frontend_flagset(result, document.id)


@router.get("/bills/{document_id}/appeal-score", summary="Appeal score (frontend shape)")
async def gateway_get_appeal_score(
    document_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    document = await _get_document_or_404(document_id, session, current_user)
    result = await _require_processed(document)
    await _record_access(
        session, user_id=current_user.id, document_id=document.id, action="read_appeal_score"
    )
    return to_frontend_appeal_score(result, document.id)


@router.post("/bills/{document_id}/appeal-score/recompute", summary="Recompute appeal score")
async def gateway_recompute_appeal_score(
    document_id: str,
    inputs: Dict[str, Any] = Body(default={}),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Return the appeal score for the bill.

    The score is derived from the bill's own facts (detected flags, denials),
    which client-supplied ``inputs`` (e.g. an edited letter) do not change, so
    this returns the current, fact-based score rather than nudging it toward a
    client-provided adjustment. A future ML recompute would re-invoke the
    scoring service here; ``inputs`` is accepted for forward compatibility.
    """
    document = await _get_document_or_404(document_id, session, current_user)
    result = await _require_processed(document)
    await _record_access(
        session,
        user_id=current_user.id,
        document_id=document.id,
        action="recompute_appeal_score",
    )
    return to_frontend_appeal_score(result, document.id)


# ---------------------------------------------------------------------------
# Letter edit + re-verification
# ---------------------------------------------------------------------------


@router.patch("/bills/{document_id}/letter", summary="Update and re-verify the appeal letter")
async def gateway_update_letter(
    document_id: str,
    body: LetterUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Edit the appeal letter and re-verify it against the underlying bill facts.

    Uses the same ``verify_letter`` core as PATCH /documents/{id}/letter (so the
    verification logic never drifts), but returns the camelCase letter shape the
    frontend consumes. The letter's ``verification_passed`` reflects a real,
    fact-checked pass over the edited text — no claim is marked verified unless
    it actually matches the parsed bill.
    """
    document = await _get_document_or_404(document_id, session, current_user)
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
        verification_passed=is_valid,
        problems=problems,
    )

    document.result_json = bill.model_dump(mode="json")
    session.add(document)
    await session.commit()

    await _record_access(
        session, user_id=current_user.id, document_id=document.id, action="update_letter"
    )

    return {
        "documentId": document_id,
        "letter": {
            "status": bill.letter.status,
            "contentMarkdown": bill.letter.content_markdown,
            "verifiedFields": list(bill.letter.verified_fields or []),
            "verificationPassed": bill.letter.verification_passed,
            "problems": list(bill.letter.problems or []),
        },
        "isFullyVerified": is_valid,
        "problems": problems,
    }
