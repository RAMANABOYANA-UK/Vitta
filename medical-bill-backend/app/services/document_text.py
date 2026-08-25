"""Extract text (+ layout) from an uploaded document for the extraction service.

This is the backend's *ingestion front door*: it turns a stored upload's bytes
into the ``raw_ocr_text`` (and optionally ``layout_json``) the extraction
pipeline consumes. It delegates to :mod:`app.services.ingestion`.

* Text-layer PDFs are read with pypdf (no OCR needed) → ``method="pdf_text"``.
* Image and scanned-PDF bills require OCR. When OCR is not enabled/available we
  raise :class:`~app.services.ingestion.IngestionError` with an honest code
  rather than silently synthesizing text. The caller surfaces that as a
  document-level error / degraded-mode notice.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.services.ingestion import DocumentExtraction, IngestionError, extract_document_content
from app.services.storage import storage_service

logger = logging.getLogger(__name__)


async def extract_document_text(
    *, storage_key: str, content_type: str
) -> DocumentExtraction:
    """Read a stored upload and return a :class:`DocumentExtraction`.

    Raises:
        IngestionError: when the document cannot be turned into text honestly
            (unreadable file, unsupported type, or OCR required but not enabled).
    """
    contents = await storage_service.get(storage_key)
    result = extract_document_content(
        contents=contents,
        content_type=content_type,
        ocr_enabled=settings.OCR_ENABLED,
    )
    logger.info(
        "Ingestion completed | method=%s | text_len=%d | content_type=%s",
        result.method,
        len(result.text),
        content_type,
    )
    return result

