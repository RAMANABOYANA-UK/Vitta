"""Unit tests for the validation service — covering mismatched totals and
invalid codes, as required by the task."""

from __future__ import annotations

import pytest
from datetime import date

from app.models import (
    DocumentMetadata,
    DocumentType,
    FieldConfidence,
    LineItem,
    ParsedBill,
    TotalsBlock,
    VerificationStatus,
)
from app.services.validation_service import ValidationService


def _make_confidence(verified: bool = False) -> FieldConfidence:
    return FieldConfidence(
        ocr_confidence=0.95,
        extraction_confidence=0.9,
        verified=verified,
    )


def _make_line(
    line_number: int,
    cpt: str = "99214",
    charge: float = 200.0,
    allowed: float = 170.0,
    paid: float = 136.0,
    patient_resp: float = 34.0,
) -> LineItem:
    return LineItem(
        line_number=line_number,
        cpt_hcpcs_code=cpt,
        charge_amount=charge,
        allowed_amount=allowed,
        paid_amount=paid,
        patient_responsibility=patient_resp,
        code_confidence=_make_confidence(),
        amount_confidence=_make_confidence(),
    )


def _make_bill(
    lines: list[LineItem],
    totals: TotalsBlock | None = None,
) -> ParsedBill:
    return ParsedBill(
        document_id="test-doc-1",
        metadata=DocumentMetadata(document_type=DocumentType.BILL),
        line_items=lines,
        totals=totals,
    )


class TestCodeValidation:
    def test_valid_cpt_code_is_verified(self):
        """A valid, active CPT code should be marked verified."""
        line = _make_line(1, cpt="99214")
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].code_confidence.verified is True
        assert result.line_items[0].code_validation is not None
        assert result.line_items[0].code_validation.status == VerificationStatus.VERIFIED
        assert result.line_items[0].code_validation.description is not None

    def test_invalid_cpt_code_is_flagged(self):
        """A code not in the reference dataset should be flagged, not silently passed."""
        line = _make_line(1, cpt="99999")  # not a real code
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].code_confidence.verified is False
        assert result.line_items[0].code_validation.status == VerificationStatus.AMBIGUOUS
        # A warning should be present
        assert any(w.code == "VERIFICATION_FAILED" for w in result.warnings)

    def test_deprecated_cpt_code_is_invalid(self):
        """A deprecated/retired code should be marked invalid."""
        line = _make_line(1, cpt="99201")  # retired 2021
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].code_confidence.verified is False
        assert result.line_items[0].code_validation.status == VerificationStatus.INVALID
        assert result.line_items[0].code_validation.is_deprecated is True

    def test_malformed_code_is_invalid(self):
        """A code that isn't even in CPT format should be invalid."""
        line = _make_line(1, cpt="12")  # too short
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].code_validation.status == VerificationStatus.INVALID

    def test_valid_icd10_is_verified(self):
        """A valid ICD-10 code should be verified."""
        line = _make_line(1)
        line.icd10_codes = ["E11.9"]
        line.icd10_confidence = _make_confidence()
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].icd10_confidence.verified is True
        assert result.line_items[0].icd10_validations[0].status == VerificationStatus.VERIFIED

    def test_invalid_icd10_is_flagged(self):
        """An invalid ICD-10 code should be flagged."""
        line = _make_line(1)
        line.icd10_codes = ["ZZZ99"]  # not a real ICD-10
        line.icd10_confidence = _make_confidence()
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].icd10_confidence.verified is False
        assert result.line_items[0].icd10_validations[0].status == VerificationStatus.INVALID


class TestAmountReconciliation:
    def test_reconciled_line_is_verified(self):
        """A line where allowed - paid = patient responsibility should be verified."""
        line = _make_line(1, charge=200.0, allowed=170.0, paid=136.0, patient_resp=34.0)
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].amount_confidence.verified is True
        assert result.line_items[0].reconciliation["matches_patient_responsibility"] is True

    def test_mismatched_line_is_flagged(self):
        """A line where allowed - paid != patient responsibility should be flagged."""
        line = _make_line(1, charge=200.0, allowed=170.0, paid=136.0, patient_resp=50.0)
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].amount_confidence.verified is False
        assert result.line_items[0].reconciliation["matches_patient_responsibility"] is False
        assert any(w.code == "AMOUNT_MISMATCH" for w in result.warnings)

    def test_charge_less_than_allowed_is_flagged(self):
        """A line where charge < allowed should be flagged."""
        line = _make_line(1, charge=100.0, allowed=170.0, paid=136.0, patient_resp=34.0)
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].amount_confidence.verified is False
        assert result.line_items[0].reconciliation["charge_ge_allowed"] is False


class TestTotalsReconciliation:
    def test_reconciled_totals_pass(self):
        """Totals where billed - adjustments - paid = patient responsibility pass."""
        totals = TotalsBlock(
            billed_total=400.0,
            adjustments_total=60.0,
            paid_total=272.0,
            patient_responsibility_total=68.0,
        )
        bill = _make_bill([], totals=totals)
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.totals.reconciliation["matches_patient_responsibility"] is True
        assert not any(w.code == "TOTALS_MISMATCH" for w in result.warnings)

    def test_mismatched_totals_are_flagged(self):
        """Totals that don't reconcile should be flagged with a warning."""
        totals = TotalsBlock(
            billed_total=400.0,
            adjustments_total=60.0,
            paid_total=272.0,
            patient_responsibility_total=100.0,  # wrong
        )
        bill = _make_bill([], totals=totals)
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.totals.reconciliation["matches_patient_responsibility"] is False
        assert any(w.code == "TOTALS_MISMATCH" for w in result.warnings)

    def test_line_sums_vs_stated_totals_mismatch(self):
        """Stated totals that don't match the sum of line items should be flagged."""
        line1 = _make_line(1, charge=200.0, allowed=170.0, paid=136.0, patient_resp=34.0)
        line2 = _make_line(2, charge=200.0, allowed=170.0, paid=136.0, patient_resp=34.0)
        # Stated billed total is wrong (should be 400)
        totals = TotalsBlock(
            billed_total=500.0,
            adjustments_total=60.0,
            paid_total=272.0,
            patient_responsibility_total=68.0,
        )
        bill = _make_bill([line1, line2], totals=totals)
        svc = ValidationService()
        result = svc.validate(bill)

        assert any(w.code == "TOTALS_VS_LINES_MISMATCH" for w in result.warnings)