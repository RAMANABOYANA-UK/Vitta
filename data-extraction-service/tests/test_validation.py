"""Unit tests for the validation service — covering mismatched totals and
invalid codes, as required by the task."""

from __future__ import annotations

import pytest
from datetime import date

from app.models import (
    DocumentStatus,
    DocumentType,
    FieldConfidence,
    Flag,
    LineItem,
    ParsedBill,
    Totals,
    VerificationStatus,
)
from app.services.validation_service import ValidationService, reconcile_amounts


def _make_confidence(verified: bool = False) -> FieldConfidence:
    return FieldConfidence(
        ocr_confidence=0.95,
        extraction_confidence=0.9,
        verified=verified,
    )


def _make_line(
    line_id: str = "LI-1",
    cpt: str = "99214",
    charge: float = 200.0,
    allowed: float = 170.0,
    paid: float = 136.0,
    patient_resp: float = 34.0,
) -> LineItem:
    return LineItem(
        id=line_id,
        cpt_hcpcs=cpt,
        charge_amount=charge,
        allowed_amount=allowed,
        paid_amount=paid,
        patient_responsibility=patient_resp,
        code_confidence=_make_confidence(),
        amount_confidence=_make_confidence(),
    )


def _make_bill(
    lines: list[LineItem],
    totals: Totals | None = None,
) -> ParsedBill:
    return ParsedBill(
        document_id="test-doc-1",
        status=DocumentStatus.processing,
        line_items=lines,
        totals=totals or Totals(),
    )


class TestCodeValidation:
    def test_valid_cpt_code_is_verified(self):
        """A valid, active CPT code should be marked verified."""
        line = _make_line(cpt="99214")
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].code_confidence.verified is True
        assert result.line_items[0].code_validation is not None
        assert result.line_items[0].code_validation.status == VerificationStatus.VERIFIED
        assert result.line_items[0].code_validation.description is not None

    def test_invalid_cpt_code_is_flagged(self):
        """A code not in the reference dataset should be flagged, not silently passed."""
        line = _make_line(cpt="99999")  # not a real code
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].code_confidence.verified is False
        assert result.line_items[0].code_validation.status == VerificationStatus.AMBIGUOUS
        # A warning should be present
        assert any(w.code == "VERIFICATION_FAILED" for w in result.warnings)

    def test_deprecated_cpt_code_is_invalid(self):
        """A deprecated/retired code should be marked invalid."""
        line = _make_line(cpt="99201")  # retired 2021
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].code_confidence.verified is False
        assert result.line_items[0].code_validation.status == VerificationStatus.INVALID
        assert result.line_items[0].code_validation.is_deprecated is True

    def test_malformed_code_is_invalid(self):
        """A code that isn't even in CPT format should be invalid."""
        line = _make_line(cpt="12")  # too short
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].code_validation.status == VerificationStatus.INVALID

    def test_valid_icd10_is_verified(self):
        """A valid ICD-10 code should be verified."""
        line = _make_line()
        line.icd10 = ["E11.9"]
        line.icd10_confidence = _make_confidence()
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].icd10_confidence.verified is True
        assert result.line_items[0].icd10_validations[0].status == VerificationStatus.VERIFIED

    def test_invalid_icd10_is_flagged(self):
        """An invalid ICD-10 code should be flagged."""
        line = _make_line()
        line.icd10 = ["ZZZ99"]  # not a real ICD-10
        line.icd10_confidence = _make_confidence()
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].icd10_confidence.verified is False
        assert result.line_items[0].icd10_validations[0].status == VerificationStatus.INVALID


class TestAmountReconciliation:
    def test_reconciled_line_is_verified(self):
        """A line where allowed - paid = patient responsibility should be verified."""
        line = _make_line(charge=200.0, allowed=170.0, paid=136.0, patient_resp=34.0)
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].amount_confidence.verified is True
        assert result.line_items[0].reconciliation["matches_patient_responsibility"] is True

    def test_mismatched_line_is_flagged(self):
        """A line where allowed - paid != patient responsibility should be flagged."""
        line = _make_line(charge=200.0, allowed=170.0, paid=136.0, patient_resp=50.0)
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].amount_confidence.verified is False
        assert result.line_items[0].reconciliation["matches_patient_responsibility"] is False
        assert any(w.code == "AMOUNT_MISMATCH" for w in result.warnings)
        # A flag should be raised on the line item (Vitta contract)
        assert any(f.type == "amount_mismatch" for f in result.line_items[0].flags)

    def test_charge_less_than_allowed_is_flagged(self):
        """A line where charge < allowed should be flagged."""
        line = _make_line(charge=100.0, allowed=170.0, paid=136.0, patient_resp=34.0)
        bill = _make_bill([line])
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.line_items[0].amount_confidence.verified is False
        assert result.line_items[0].reconciliation["charge_ge_allowed"] is False


class TestTotalsReconciliation:
    def test_reconciled_totals_pass(self):
        """Totals where billed - adjustments - paid = patient responsibility pass."""
        totals = Totals(
            billed=400.0,
            allowed=340.0,
            insurance_paid=272.0,
            patient_responsibility=68.0,
        )
        bill = _make_bill([], totals=totals)
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.totals.reconciliation["matches_patient_responsibility"] is True
        assert not any(w.code == "TOTALS_MISMATCH" for w in result.warnings)

    def test_mismatched_totals_are_flagged(self):
        """Totals that don't reconcile should be flagged with a warning."""
        totals = Totals(
            billed=400.0,
            allowed=340.0,
            insurance_paid=272.0,
            patient_responsibility=100.0,  # wrong
        )
        bill = _make_bill([], totals=totals)
        svc = ValidationService()
        result = svc.validate(bill)

        assert result.totals.reconciliation["matches_patient_responsibility"] is False
        assert any(w.code == "TOTALS_MISMATCH" for w in result.warnings)

    def test_line_sums_vs_stated_totals_mismatch(self):
        """Stated totals that don't match the sum of line items should be flagged."""
        line1 = _make_line("LI-1", charge=200.0, allowed=170.0, paid=136.0, patient_resp=34.0)
        line2 = _make_line("LI-2", charge=200.0, allowed=170.0, paid=136.0, patient_resp=34.0)
        # Stated billed total is wrong (should be 400)
        totals = Totals(
            billed=500.0,
            allowed=340.0,
            insurance_paid=272.0,
            patient_responsibility=68.0,
        )
        bill = _make_bill([line1, line2], totals=totals)
        svc = ValidationService()
        result = svc.validate(bill)

        assert any(w.code == "TOTALS_VS_LINES_MISMATCH" for w in result.warnings)

    def test_totals_honor_extracted_adjustments_total(self):
        """An extracted adjustments_total is recorded (previously dead), and the
        two-way invariant allowed == paid + patient_responsibility drives pass/fail."""
        totals = Totals(
            billed=500.0,
            allowed=340.0,
            insurance_paid=272.0,
            patient_responsibility=68.0,
            adjustments_total=160.0,  # stated on the bill, but unused before
        )
        bill = _make_bill([], totals=totals)
        svc = ValidationService()
        result = svc.validate(bill)

        rec = result.totals.reconciliation
        # The check uses the reduced two-way invariant, so it still passes...
        assert rec["matches_patient_responsibility"] is True
        # ...and the extracted value is now surfaced instead of being dropped.
        assert rec["adjustments_total"] == 160.0
        assert not any(w.code == "TOTALS_MISMATCH" for w in result.warnings)


class TestReconcileAmountsHelper:
    def test_reconcile_amounts_matching(self):
        """reconcile_amounts should return no warnings when amounts match."""
        line_items = [
            {"id": "LI-1", "charge_amount": 200.0, "allowed_amount": 170.0,
             "paid_amount": 136.0, "patient_responsibility": 34.0}
        ]
        totals = {"billed": 200.0}
        warnings = reconcile_amounts(line_items, totals)
        assert warnings == []

    def test_reconcile_amounts_line_sum_mismatch(self):
        """reconcile_amounts should flag line-sum vs totals.billed mismatch."""
        line_items = [
            {"id": "LI-1", "charge_amount": 200.0, "allowed_amount": 170.0,
             "paid_amount": 136.0, "patient_responsibility": 34.0}
        ]
        totals = {"billed": 500.0}  # wrong
        warnings = reconcile_amounts(line_items, totals)
        assert any(w["type"] == "amount_mismatch" for w in warnings)

    def test_reconcile_amounts_patient_resp_mismatch(self):
        """reconcile_amounts should flag patient_responsibility mismatch."""
        line_items = [
            {"id": "LI-1", "charge_amount": 200.0, "allowed_amount": 170.0,
             "paid_amount": 136.0, "patient_responsibility": 50.0}  # wrong
        ]
        totals = {"billed": 200.0}
        warnings = reconcile_amounts(line_items, totals)
        assert any(w["type"] == "line_reconciliation" for w in warnings)

    def test_reconcile_amounts_never_invents_totals(self):
        """reconcile_amounts should not flag when totals are missing."""
        line_items = [
            {"id": "LI-1", "charge_amount": 200.0, "allowed_amount": 170.0,
             "paid_amount": 136.0, "patient_responsibility": 34.0}
        ]
        totals = {}  # no billed total
        warnings = reconcile_amounts(line_items, totals)
        assert warnings == []
