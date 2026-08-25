from unittest.mock import AsyncMock, patch
from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.services.document_text import extract_document_text


@pytest.mark.asyncio
async def test_image_upload_fails_until_ocr_is_configured():
    with pytest.raises(RuntimeError, match="Image OCR is not configured"):
        await extract_document_text(storage_key="bill.jpg", content_type="image/jpeg")


@pytest.mark.asyncio
async def test_scanned_pdf_fails_instead_of_returning_empty_text():
    pdf = BytesIO()
    PdfWriter().write(pdf)
    with patch(
        "app.services.document_text.storage_service.get",
        new=AsyncMock(return_value=pdf.getvalue()),
    ):
        with pytest.raises(RuntimeError, match="no selectable text"):
            await extract_document_text(
                storage_key="bill.pdf", content_type="application/pdf"
            )
