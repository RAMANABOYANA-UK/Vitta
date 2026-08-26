"""Ingestion front door: turn an uploaded byte stream into raw OCR text + layout.

Until now ``raw_ocr_text`` and ``layout_json`` were *inputs* to the extraction
pipeline — components upstream were expected to have produced them, and nothing
in the repo did. This module is that missing front door. It is deliberately
small and dependency-light:

* PDFs with a selectable text layer are read with pypdf, producing text and a
  minimal per-page ``layout_json`` (page size + char count). This needs no OCR.
* Images (JPEG/PNG/WEBP) and scanned (text-less) PDFs require an OCR provider.
  OCR is behind a flag (``OCR_ENABLED``) and the pytesseract dependency is
  imported lazily, so a deployment without OCR still works — it just reports an
  honest ``IngestionError`` instead of silently fabricating text.

Every code path returns a :class:`DocumentExtraction` carrying the extraction
``method`` so the rest of the system can be honest about whether a real
document was read (``pdf_text``/``ocr``) or the pipeline fell back to sample
data. No method is ever implied that did not run.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Content types accepted by the upload endpoints (kept in sync with
# app.api.routes.documents.ALLOWED_CONTENT_TYPES).
_PDF_CONTENT_TYPE = "application/pdf"
_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class IngestionError(RuntimeError):
    """Raised when a document cannot be turned into text.

    ``code`` is a machine-readable identifier the API/UI can key off, and the
    message is a safe (non-PHI) human explanation.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class DocumentExtraction:
    """The result of turning an uploaded file into structured text.

    Attributes:
        text:        Not-None raw OCR / extracted text (empty means nothing was
                     read, which callers should treat as a failure).
        method:      How ``text`` was produced: ``"pdf_text"`` (selectable PDF
                     layer), ``"ocr"`` (image / scanned PDF via OCR), or
                     ``"none"`` (nothing read). Never fabricated.
        layout_json: Optional layout metadata (page size, char counts). May be
                     ``None`` when the reader provides no layout info.
        warnings:    Human-readable, non-PHI notes (e.g. OCR provider absent).
        content_type: The content type that was ingested.
    """

    text: str = ""
    method: str = "none"
    layout_json: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    content_type: str = ""


def _open_pdf_reader(contents: bytes) -> Any:
    """Open a pypdf reader, raising IngestionError on failure."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - env without pypdf
        raise IngestionError(
            "pdf_reader_unavailable",
            "PDF text extraction is unavailable because pypdf is not installed.",
        ) from exc
    try:
        return PdfReader(io.BytesIO(contents))
    except Exception as exc:
        raise IngestionError(
            "unreadable_pdf", "The uploaded PDF could not be read."
        ) from exc


def _pdf_layout(reader: Any) -> Optional[Dict[str, Any]]:
    """Build a best-effort layout_json from a pypdf reader.

    Layout is defensive: a reader/page that lacks media-box info just
    contributes no entry rather than raising.
    """
    try:
        pages: List[Dict[str, Any]] = []
        for idx, page in enumerate(reader.pages):
            entry: Dict[str, Any] = {"page": idx + 1}
            mb = getattr(page, "mediabox", None)
            if mb is not None:
                try:
                    entry["width"] = float(mb.width)
                    entry["height"] = float(mb.height)
                except (TypeError, ValueError):
                    pass
            try:
                raw = page.extract_text() or ""
                entry["text_len"] = len(raw.strip())
            except Exception:  # pragma: no cover - defensive per-page
                entry["text_len"] = 0
            pages.append(entry)
        return {"engine": "pypdf", "pages": pages}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not build layout_json: %s", exc)
        return None


def _pdf_text(reader: Any) -> str:
    """Return concatenated selectable text of a PDF, or ``""`` if none."""
    chunks = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # pragma: no cover - defensive per-page
            text = ""
        if text.strip():
            chunks.append(text)
    return "\n".join(chunks).strip()


def _ocr_image_text(contents: bytes, lang: str = "eng") -> str:
    """OCRed text from an image via pytesseract."""
    try:
        import pytesseract  # type: ignore
        from PIL import Image, UnidentifiedImageError  # type: ignore
    except ImportError as exc:
        raise IngestionError(
            "ocr_not_configured",
            "Image OCR is not configured (pytesseract/Pillow not installed).",
        ) from exc
    try:
        image = Image.open(io.BytesIO(contents))
        image.load()
        return (pytesseract.image_to_string(image, lang=lang) or "").strip()
    except (UnidentifiedImageError, OSError) as exc:
        raise IngestionError(
            "unreadable_image", "The uploaded image could not be read for OCR."
        ) from exc
    except Exception as exc:  # pragma: no cover - tesseract binary errors
        raise IngestionError(
            "ocr_failed",
            "OCR could not be run on this image (is the tesseract binary installed and on PATH?).",
        ) from exc


def _ocr_available() -> bool:
    """Return True only if pytesseract is installed AND a tesseract binary is reachable.

    This is the honest gate: OCR code paths exist, but actually running them needs
    the tesseract engine. We never claim OCR worked unless the binary is present.
    """
    try:
        import pytesseract  # type: ignore
    except ImportError:
        return False
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


def _ocr_scanned_pdf(contents: bytes, lang: str = "eng") -> str:
    """OCR a scanned (text-less) PDF: rasterize each page with PyMuPDF, then run
    pytesseract over every page image. Returns concatenated page text.

    Raises IngestionError with an honest code when the renderer or OCR engine is
    unavailable or the PDF cannot be rasterized.
    """
    try:
        import pymupdf  # type: ignore
    except ImportError:  # pragma: no cover - env without pymupdf
        raise IngestionError(
            "pdf_ocr_unavailable",
            "Scanned-PDF OCR requires PyMuPDF (pymupdf) to rasterize pages, which is not installed.",
        )
    try:
        import pytesseract  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise IngestionError(
            "ocr_not_configured",
            "Scanned-PDF OCR requires pytesseract, which is not installed.",
        ) from exc

    if not _ocr_available():
        raise IngestionError(
            "ocr_not_configured",
            "OCR is enabled but no tesseract binary is available. Install tesseract and ensure it is on PATH.",
        )

    try:
        doc = pymupdf.open(stream=contents, filetype="pdf")
    except Exception as exc:
        raise IngestionError(
            "unreadable_pdf", "The scanned PDF could not be opened for OCR."
        ) from exc

    chunks: List[str] = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=200)  # reasonable OCR resolution
            img_bytes = pix.tobytes("png")
            chunks.append(_ocr_image_text(img_bytes, lang=lang))
    except Exception as exc:  # pragma: no cover - defensive
        raise IngestionError(
            "ocr_failed", "OCR could not be run on a page of this PDF."
        ) from exc
    finally:
        doc.close()
    return "\n".join(c for c in chunks if c).strip()


def extract_document_content(
    *, contents: bytes, content_type: str, ocr_enabled: bool = False
) -> DocumentExtraction:
    """Extract text + layout from an uploaded byte stream.

    Args:
        contents:     Raw file bytes (already size-validated upstream).
        content_type: MIME type of the upload.
        ocr_enabled:  Whether OCR providers may be used (see ``OCR_ENABLED``).

    Raises:
        IngestionError: with an honest ``code`` when the file has no selectable
            text and OCR is unavailable/unconfigured, or the file is unreadable.
    """
    ct = (content_type or "").lower()

    if ct == _PDF_CONTENT_TYPE:
        reader = _open_pdf_reader(contents)
        text = _pdf_text(reader)
        if text:
            return DocumentExtraction(
                text=text,
                method="pdf_text",
                layout_json=_pdf_layout(reader),
                content_type=ct,
            )
        # Scanned PDF: no selectable text layer — run OCR when enabled.
        if not ocr_enabled:
            raise IngestionError(
                "scanned_pdf_needs_ocr",
                "This PDF has no selectable text (it is a scan). Enable OCR to read it.",
            )
        ocr_text = _ocr_scanned_pdf(contents)
        if not ocr_text:
            raise IngestionError(
                "no_ocr_text", "OCR produced no readable text from this scanned PDF."
            )
        return DocumentExtraction(
            text=ocr_text,
            method="ocr",
            layout_json=_pdf_layout(reader),
            content_type=ct,
        )

    if ct in _IMAGE_CONTENT_TYPES:
        if not ocr_enabled:
            raise IngestionError(
                "ocr_not_configured",
                "Image OCR is not configured. Enable OCR to read image bills.",
            )
        if not _ocr_available():
            raise IngestionError(
                "ocr_not_configured",
                "OCR is enabled but no tesseract binary is available. Install "
                "tesseract and ensure it is on PATH.",
            )
        text = _ocr_image_text(contents)
        if not text:
            raise IngestionError(
                "no_ocr_text", "OCR produced no readable text from this image."
            )
        return DocumentExtraction(
            text=text, method="ocr", layout_json=None, content_type=ct
        )

    raise IngestionError(
        "unsupported_content_type",
        f"Unsupported content type for ingestion: {content_type or '(none)'}",
    )

