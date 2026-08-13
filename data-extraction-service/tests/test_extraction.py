"""Unit tests for the extraction pipeline (heuristic fallback path)."""

from __future__ import annotations

from app.models import DocumentType
from app.services.extractor import ExtractionRequest, ExtractionService


def _make_service() -> ExtractionService:
    """Force heuristic mode (no LLM key configured in tests)."""
    svc = ExtractionService()
    svc.llm_configured = False
    return svc


class TestExtraction:
    def test_extracts_bill_with_cpt_codes(self):
        """A simple bill with CPT codes should extract line items."""
        text = (
            "Provider: City Medical Group\n"
            "NPI: 1234567890\n"
            "Payer: Blue Cross\n"
            "Account No: ACCT-12345\n"
            "Statement Date: 01/15/2024\n"
            "Date of Service: 01/10/2024\n"
            "99214 Office visit $200.00\n"
            "93000 ECG $45.00\n"
            "Total Billed: $245.00\n"
        )
        svc = _make_service()
        result = svc.extract(ExtractionRequest(raw_ocr_text=text))

        assert result.metadata.document_type == DocumentType.BILL
        assert result.metadata.provider_name == "City Medical Group"
        assert result.metadata.provider_npi == "1234567890"
        assert result.metadata.payer_name == "Blue Cross"
        assert result.metadata.patient_account_ref is not None
        assert result.metadata.patient_account_ref.startswith("acct-")
        assert len(result.line_items) == 2
        assert result.line_items[0].cpt_hcpcs_code == "99214"
        assert result.line_items[0].charge_amount == 200.0
        assert result.line_items[1].cpt_hcpcs_code == "93000"
        assert result.totals is not None
        assert result.totals.billed_total == 245.0

    def test_extracts_eob_with_allowed_paid(self):
        """An EOB should extract allowed/paid/patient-responsibility amounts."""
        text = (
            "EXPLANATION OF BENEFITS\n"
            "Provider: City Medical Group\n"
            "Payer: Blue Cross\n"
            "99214 Office visit $200.00 $170.00 $136.00 $34.00\n"
            "Total Billed: $200.00\n"
            "Total Allowed: $170.00\n"
            "Total Paid: $136.00\n"
            "Total Patient Responsibility: $34.00\n"
        )
        svc = _make_service()
        result = svc.extract(ExtractionRequest(raw_ocr_text=text))

        assert result.metadata.document_type == DocumentType.EOB
        assert len(result.line_items) == 1
        line = result.line_items[0]
        assert line.charge_amount == 200.0
        assert line.allowed_amount == 170.0
        assert line.paid_amount == 136.0
        assert line.patient_responsibility == 34.0
        assert result.totals is not None
        assert result.totals.patient_responsibility_total == 34.0

    def test_low_confidence_flagged(self):
        """Low-confidence OCR regions should produce warnings."""
        text = "99214 Office visit $200.00"
        layout = {
            "blocks": [
                {
                    "text": "99214 Office visit $200.00",
                    "confidence": 0.4,  # low
                    "page": 1,
                    "bounding_box": [0.1, 0.1, 0.5, 0.2],
                }
            ]
        }
        svc = _make_service()
        result = svc.extract(ExtractionRequest(raw_ocr_text=text, layout_json=layout))

        assert any(w.code == "LOW_CONF" for w in result.warnings)

    def test_multipage_table_flagged(self):
        """Multi-page tables should be flagged."""
        text = "99214 $200.00"
        layout = {
            "tables": [
                {
                    "id": "t1",
                    "page": 1,
                    "rows": [
                        {"cells": [{"text": "99214", "page": 1}, {"text": "$200.00", "page": 1}]}
                    ],
                },
                {
                    "id": "t2",
                    "page": 2,
                    "rows": [
                        {"cells": [{"text": "93000", "page": 2}, {"text": "$45.00", "page": 2}]}
                    ],
                },
            ]
        }
        svc = _make_service()
        result = svc.extract(ExtractionRequest(raw_ocr_text=text, layout_json=layout))

        assert any(w.code == "MULTIPAGE_TABLE" for w in result.warnings)

    def test_handwriting_flagged(self):
        """Handwriting detection should produce a warning."""
        text = "99214 $200.00"
        layout = {"is_handwritten": True}
        svc = _make_service()
        result = svc.extract(ExtractionRequest(raw_ocr_text=text, layout_json=layout))

        assert any(w.code == "HANDWRITING_DETECTED" for w in result.warnings)

    def test_provenance_preserved(self):
        """Extracted values should carry provenance (page, bbox)."""
        text = "99214 Office visit $200.00"
        layout = {
            "blocks": [
                {
                    "text": "99214 Office visit $200.00",
                    "confidence": 0.95,
                    "page": 2,
                    "bounding_box": [0.1, 0.1, 0.5, 0.2],
                }
            ]
        }
        svc = _make_service()
        result = svc.extract(ExtractionRequest(raw_ocr_text=text, layout_json=layout))

        assert len(result.line_items) == 1
        prov = result.line_items[0].code_confidence.provenance
        assert prov is not None
        assert prov.page == 2
        assert prov.bounding_box == [0.1, 0.1, 0.5, 0.2]