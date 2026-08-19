"""
Document text extraction service.

Extracts usable text from uploaded medical bill documents (PDFs and images)
so that Member 2's extraction service receives real content instead of
placeholder strings.

Design:
- PDFs: extract embedded text via pypdf (fast, no external services)
- Images: optional OCR via pytesseract (local) or a pluggable OCR provider
  (Textract / Document AI) controlled by OCR_PROVIDER
- Graceful fallback: if extraction fails, returns a structured result with
  `text=None` and a clear `error` so the caller can decide how to proceed
"""

import io
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ExtractedText:
    """Result of document text extraction."""

    text: Optional[str]
    method: str  # "pdf_text" | "ocr" | "none"
    pages: int = 0
    confidence: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


async def extract_text_from_bytes(
    content: bytes,
    content_type: str,
    original_filename: str = "",
) -> ExtractedText:
    """
    Extract usable text from a document's raw bytes.

    Returns an ExtractedText with:
    - text: the extracted text (or None if extraction failed)
    - method: which extraction path was used
    - error: a message if extraction failed
    """
    content_type = (content_type or "").lower()

    # PDF path
    if "pdf" in content_type or original_filename.lower().endswith(".pdf"):
        return await _extract_pdf_text(content)

    # Image path (OCR)
    if any(t in content_type for t in ("image", "jpeg", "png", "tiff", "webp")):
        return await _extract_image_ocr(content, content_type)

    # Unknown type — try PDF extraction as a last resort, then OCR
    logger.warning(
        "Unknown content type '%s' for %s — attempting PDF then OCR",
        content_type,
        original_filename,
    )
    result = await _extract_pdf_text(content)
    if result.text:
        return result
    return await _extract_image_ocr(content, content_type)


async def _extract_pdf_text(content: bytes) -> ExtractedText:
    """Extract embedded text from a PDF using pypdf."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        pages_text: list[str] = []
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            pages_text.append(page_text)

        full_text = "\n\n".join(pages_text).strip()
        if not full_text:
            return ExtractedText(
                text=None,
                method="pdf_text",
                pages=len(reader.pages),
                error="PDF contains no embedded text (scanned document — OCR required)",
            )

        logger.info(
            "PDF text extraction succeeded | pages=%d | chars=%d",
            len(reader.pages),
            len(full_text),
        )
        return ExtractedText(
            text=full_text,
            method="pdf_text",
            pages=len(reader.pages),
            confidence=1.0,
        )
    except ImportError:
        logger.warning("pypdf not installed — cannot extract PDF text")
        return ExtractedText(
            text=None,
            method="pdf_text",
            error="pypdf not installed; install with: pip install pypdf",
        )
    except Exception as e:
        logger.warning("PDF text extraction failed: %s", str(e))
        return ExtractedText(
            text=None,
            method="pdf_text",
            error=f"PDF text extraction failed: {str(e)}",
        )


async def _extract_image_ocr(content: bytes, content_type: str) -> ExtractedText:
    """
    OCR an image. Uses the configured OCR provider:
    - "tesseract": local pytesseract (default, zero external deps)
    - "textract": AWS Textract (requires boto3 + credentials)
    - "docai": Google Document AI (requires google-cloud-documentai)
    """
    provider = settings.OCR_PROVIDER.lower()

    if provider == "textract":
        return await _extract_textract(content)
    if provider == "docai":
        return await _extract_docai(content)

    # Default: local tesseract
    return await _extract_tesseract(content)


async def _extract_tesseract(content: bytes) -> ExtractedText:
    """Local OCR via pytesseract."""
    try:
        from PIL import Image
        import pytesseract

        image = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(image)
        text = text.strip()

        if not text:
            return ExtractedText(
                text=None,
                method="ocr",
                error="OCR produced no text",
            )

        logger.info("Tesseract OCR succeeded | chars=%d", len(text))
        return ExtractedText(
            text=text,
            method="ocr",
            confidence=None,  # tesseract doesn't give a single confidence
        )
    except ImportError:
        logger.warning(
            "pytesseract/Pillow not installed — cannot OCR image. "
            "Install with: pip install pytesseract Pillow"
        )
        return ExtractedText(
            text=None,
            method="ocr",
            error="pytesseract/Pillow not installed for OCR",
        )
    except Exception as e:
        logger.warning("Tesseract OCR failed: %s", str(e))
        return ExtractedText(
            text=None,
            method="ocr",
            error=f"OCR failed: {str(e)}",
        )


async def _extract_textract(content: bytes) -> ExtractedText:
    """AWS Textract OCR (requires boto3 + AWS credentials)."""
    try:
        import boto3

        client = boto3.client(
            "textract",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        response = client.detect_document_text(Document={"Bytes": content})

        blocks = response.get("Blocks", [])
        lines = [
            b["Text"]
            for b in blocks
            if b.get("BlockType") == "LINE" and b.get("Text")
        ]
        text = "\n".join(lines).strip()

        if not text:
            return ExtractedText(
                text=None,
                method="ocr",
                error="Textract produced no text",
            )

        logger.info("Textract OCR succeeded | chars=%d", len(text))
        return ExtractedText(
            text=text,
            method="ocr",
            confidence=response.get("DetectDocumentTextModelVersion"),
        )
    except ImportError:
        return ExtractedText(
            text=None,
            method="ocr",
            error="boto3 not installed for Textract OCR",
        )
    except Exception as e:
        logger.warning("Textract OCR failed: %s", str(e))
        return ExtractedText(
            text=None,
            method="ocr",
            error=f"Textract OCR failed: {str(e)}",
        )


async def _extract_docai(content: bytes) -> ExtractedText:
    """Google Document AI OCR (requires google-cloud-documentai)."""
    try:
        from google.cloud import documentai_v1 as documentai

        client = documentai.DocumentProcessorServiceClient()
        name = client.processor_path(
            settings.DOCAI_PROJECT_ID,
            settings.DOCAI_LOCATION,
            settings.DOCAI_PROCESSOR_ID,
        )
        document = documentai.types.Document(
            content=content,
            mime_type="application/pdf",
        )
        request = documentai.types.ProcessRequest(name=name, raw_document=document)
        result = client.process_document(request=request)

        text = result.document.text.strip()
        if not text:
            return ExtractedText(
                text=None,
                method="ocr",
                error="Document AI produced no text",
            )

        logger.info("Document AI OCR succeeded | chars=%d", len(text))
        return ExtractedText(
            text=text,
            method="ocr",
            confidence=None,
        )
    except ImportError:
        return ExtractedText(
            text=None,
            method="ocr",
            error="google-cloud-documentai not installed for Document AI OCR",
        )
    except Exception as e:
        logger.warning("Document AI OCR failed: %s", str(e))
        return ExtractedText(
            text=None,
            method="ocr",
            error=f"Document AI OCR failed: {str(e)}",
        )