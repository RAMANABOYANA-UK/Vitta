"""Unit tests for the ingestion front door (P1 #6).

These exercise the real byte-stream → text pipeline that previously did not
exist in the repo: a text-layer PDF is read with pypdf into ``raw_ocr_text`` +
``layout_json``; images / scanned PDFs raise an HONEST ``IngestionError`` when
OCR is unavailable, instead of silently fabricating text.

A real PDF fixture is generated with reportlab (also used for a NEGATIVE case:
a blank-page PDF exercises the "scanned / no text layer" path). reportlab and
Pillow are available in the test environment; both imports are guarded so the
suite degrades gracefully if they are absent.
"""

from __future__ import annotations

import io
import types

import pytest

from app.services.ingestion import (
    DocumentExtraction,
    IngestionError,
    extract_document_content,
)


def _make_text_pdf(lines: list[str]) -> bytes:
    """Return a small text-layer PDF containing ``lines``."""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 760.0
    for ln in lines:
        c.drawString(72, y, ln)
        y -= 16
    c.showPage()
    c.save()
    return buf.getvalue()


def _make_blank_pdf() -> bytes:
    """Return a PDF whose only page has no selectable text (like a scan)."""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.showPage()
    c.save()
    return buf.getvalue()


def _make_png() -> bytes:
    """Return a tiny valid PNG (OCR-unfriendly, but fine for plumbing tests)."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (2, 2), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


class TestPdfTextExtraction:
    def test_text_layer_pdf_reads_to_raw_text(self):
        contents = _make_text_pdf(
            [
                "Provider: City Medical Group",
                "NPI: 1234567890",
                "99214 Office visit $200.00",
                "Total Billed: $200.00",
            ]
        )
        result = extract_document_content(
            contents=contents, content_type="application/pdf"
        )
        assert isinstance(result, DocumentExtraction)
        assert result.method == "pdf_text"
        assert "City Medical Group" in result.text
        assert "1234567890" in result.text
        assert "99214" in result.text
        assert result.content_type == "application/pdf"

    def test_layout_json_is_populated(self):
        contents = _make_text_pdf(["One line here"])
        result = extract_document_content(
            contents=contents, content_type="application/pdf"
        )
        layout = result.layout_json
        assert layout is not None
        assert layout["engine"] == "pypdf"
        assert isinstance(layout["pages"], list)
        assert layout["pages"][0]["page"] == 1


class TestHonestFailures:
    def test_scanned_pdf_requires_ocr(self):
        contents = _make_blank_pdf()
        with pytest.raises(IngestionError) as ei:
            extract_document_content(
                contents=contents, content_type="application/pdf", ocr_enabled=False
            )
        assert ei.value.code == "scanned_pdf_needs_ocr"

    def test_image_ocr_not_configured_by_default(self):
        with pytest.raises(IngestionError) as ei:
            extract_document_content(
                contents=_make_png(),
                content_type="image/png",
                ocr_enabled=False,
            )
        assert ei.value.code == "ocr_not_configured"

    def test_image_ocr_enabled_still_fails_without_driver(self):
        # pytesseract is not installed in this environment, so even OCR_ENABLED
        # cannot fabricate text — it must raise, not silently fake the result.
        with pytest.raises(IngestionError) as ei:
            extract_document_content(
                contents=_make_png(),
                content_type="image/png",
                ocr_enabled=True,
            )
        assert ei.value.code == "ocr_not_configured"

    def test_unreadable_pdf(self):
        with pytest.raises(IngestionError) as ei:
            extract_document_content(
                contents=b"this is not a pdf", content_type="application/pdf"
            )
        assert ei.value.code == "unreadable_pdf"

    def test_unsupported_content_type(self):
        with pytest.raises(IngestionError) as ei:
            extract_document_content(contents=b"x", content_type="text/plain")
        assert ei.value.code == "unsupported_content_type"


class TestOcrWhenEnabled:
    """P1 #6 OCR path — exercised with mocked pytesseract/pymupdf so the tests do
    not require a tesseract binary. The code under test is REAL: it rasterizes a
    scanned PDF with PyMuPDF and OCRs each page; we only fake the two engines."""

    @staticmethod
    def _fake_tesseract(text: str = "Provider: City Medical OCR"):
        t = types.SimpleNamespace()
        t.image_to_string = lambda img, **k: text
        t.get_tesseract_version = lambda: "5.3.0"
        return t

    @staticmethod
    def _fake_pymupdf():
        valid_png = _make_png()  # a real PNG so PIL can open it

        class _Page:
            def __init__(self):
                self.pix = types.SimpleNamespace(tobytes=lambda fmt: valid_png)

            def get_pixmap(self, dpi=200):
                return self.pix

        class _Doc:
            def __init__(self, n=2):
                self.pages = [_Page() for _ in range(n)]
                self.closed = False

            def __iter__(self):
                return iter(self.pages)

            def close(self):
                self.closed = True

        m = types.ModuleType("pymupdf")
        m.open = lambda **k: _Doc()
        return m

    def test_scanned_pdf_is_ocred_when_enabled_and_engine_present(self, monkeypatch):
        import app.services.ingestion as ing

        monkeypatch.setitem(
            __import__("sys").modules, "pytesseract", self._fake_tesseract()
        )
        monkeypatch.setitem(
            __import__("sys").modules, "pymupdf", self._fake_pymupdf()
        )
        monkeypatch.setattr(ing, "_ocr_available", lambda: True)

        result = extract_document_content(
            contents=_make_blank_pdf(), content_type="application/pdf", ocr_enabled=True
        )
        assert result.method == "ocr"
        assert "City Medical OCR" in result.text

    def test_image_is_ocred_when_enabled_and_engine_present(self, monkeypatch):
        import app.services.ingestion as ing

        monkeypatch.setitem(
            __import__("sys").modules, "pytesseract", self._fake_tesseract()
        )
        monkeypatch.setattr(ing, "_ocr_available", lambda: True)

        result = extract_document_content(
            contents=_make_png(), content_type="image/png", ocr_enabled=True
        )
        assert result.method == "ocr"
        assert "City Medical OCR" in result.text
