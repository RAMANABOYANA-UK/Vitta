"""Extract text from an uploaded document for the extraction service."""

from __future__ import annotations

import asyncio
import io

from app.services.storage import storage_service


async def extract_document_text(*, storage_key: str, content_type: str) -> str:
    """Read a stored upload and return text suitable for OCR extraction.

    Text-based PDFs are supported locally through pypdf. Image uploads require
    a configured OCR provider and fail explicitly until that provider is wired.
    """
    if content_type != "application/pdf":
        raise RuntimeError(
            "Image OCR is not configured. Configure an OCR provider before processing image bills."
        )
    contents = await storage_service.get(storage_key)
    return await asyncio.to_thread(_extract_pdf_text, contents)


def _extract_pdf_text(contents: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF text extraction is unavailable because pypdf is not installed."
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(contents))
    except Exception as exc:
        raise RuntimeError("The uploaded PDF could not be read.") from exc
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise RuntimeError(
            "The PDF contains no selectable text. Configure OCR for scanned bills."
        )
    return text
