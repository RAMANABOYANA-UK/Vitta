from unittest.mock import AsyncMock, patch
from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.services.document_text import extract_document_text
from app.services.ingestion import DocumentExtraction, IngestionError


def _make_png() -> bytes:
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (2, 2), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_image_upload_fails_until_ocr_is_configured():
    """An image bill with OCR disabled raises an HONEST error (no fabrication)."""
    with patch(
        "app.services.document_text.storage_service.get",
        new=AsyncMock(return_value=_make_png()),
    ):
        with pytest.raises(IngestionError) as ei:
            await extract_document_text(storage_key="bill.jpg", content_type="image/jpeg")
        assert ei.value.code == "ocr_not_configured"
        assert "Image OCR is not configured" in str(ei.value)


@pytest.mark.asyncio
async def test_scanned_pdf_fails_instead_of_returning_empty_text():
    pdf = BytesIO()
    PdfWriter().write(pdf)
    with patch(
        "app.services.document_text.storage_service.get",
        new=AsyncMock(return_value=pdf.getvalue()),
    ):
        with pytest.raises(IngestionError) as ei:
            await extract_document_text(
                storage_key="bill.pdf", content_type="application/pdf"
            )
        assert ei.value.code == "scanned_pdf_needs_ocr"
        assert "no selectable text" in str(ei.value)


@pytest.mark.asyncio
async def test_text_pdf_returns_rich_extraction():
    """A text-layer PDF is read into text + method + layout (the real front door)."""

    def _make_pdf() -> bytes:
        from reportlab.pdfgen import canvas

        buf = BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 720, "Provider: City Medical Group")
        c.drawString(72, 704, "99214 Office visit $200.00")
        c.showPage()
        c.save()
        return buf.getvalue()

    with patch(
        "app.services.document_text.storage_service.get",
        new=AsyncMock(return_value=_make_pdf()),
    ):
        result = await extract_document_text(
            storage_key="bill.pdf", content_type="application/pdf"
        )
    assert isinstance(result, DocumentExtraction)
    assert result.method == "pdf_text"
    assert "City Medical Group" in result.text
    assert result.layout_json is not None

