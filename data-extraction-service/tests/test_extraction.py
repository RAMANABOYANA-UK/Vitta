"""Unit tests for the extraction pipeline (heuristic fallback path)."""

from __future__ import annotations

from app.models import DocumentType, SourceType
from app.services.extractor import (
    ExtractionRequest,
    ExtractionService,
    find_amounts,
    find_codes,
)


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

    def test_messy_ocr_extracts_line_items(self):
        """Messy OCR text with noise should still extract structured line items."""
        text = (
            "Provider: City Medical Group\n"
            "NPI: 1234567893\n"
            "Claim Number: GX-2025-883241\n"
            "Service Date: 07/22/2026\n"
            "CPT 99284 ER visit $1,240.00\n"
            "Allowed $800.00 Paid $650.00 Patient Resp $150.00\n"
            "Denial CO-97 Bundled service\n"
            "Total Billed: $1,240.00\n"
        )
        svc = _make_service()
        result = svc.extract(ExtractionRequest(raw_ocr_text=text))

        assert result.source_type == SourceType.BILL
        assert len(result.line_items) == 1
        line = result.line_items[0]
        assert line.cpt_hcpcs == "99284"
        assert line.charge_amount == 1240.0
        assert line.allowed_amount == 800.0
        assert line.paid_amount == 650.0
        assert line.patient_responsibility == 150.0
        # Claim number should be captured in metadata confidence
        assert "claim_number" in result.metadata.metadata_confidence

    def test_messy_ocr_eob_source_type(self):
        """EOB OCR text should map to source_type='eob'."""
        text = (
            "EXPLANATION OF BENEFITS\n"
            "Provider: City Medical Group\n"
            "99214 Office visit $200.00 $170.00 $136.00 $34.00\n"
            "Total Billed: $200.00\n"
        )
        svc = _make_service()
        result = svc.extract(ExtractionRequest(raw_ocr_text=text))

        assert result.source_type == SourceType.EOB

    def test_find_codes_utility(self):
        """find_codes should extract CPT/HCPCS codes from messy text."""
        text = "CPT 99284 ER visit, HCPCS G0463 lab, 99214 follow-up"
        codes = find_codes(text)
        assert "99284" in codes
        assert "G0463" in codes
        assert "99214" in codes

    def test_find_amounts_utility(self):
        """find_amounts should extract monetary amounts from messy text."""
        text = "Charge $1,240.00 Allowed 800.00 Paid 650 Patient Resp $150.00"
        amounts = find_amounts(text)
        assert 1240.0 in amounts
        assert 800.0 in amounts
        assert 650.0 in amounts
        assert 150.0 in amounts

    def test_icd10_extracted_from_line_window(self):
        """ICD-10 codes should be extracted from line item windows."""
        text = (
            "Provider: City Medical Group\n"
            "99214 Office visit ICD-10: E11.9, I10 $200.00\n"
            "Total Billed: $200.00\n"
        )
        svc = _make_service()
        result = svc.extract(ExtractionRequest(raw_ocr_text=text))

        assert len(result.line_items) == 1
        line = result.line_items[0]
        assert "E11.9" in line.icd10
        assert "I10" in line.icd10
