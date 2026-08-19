"""Validation service — validates codes and reconciles amounts.

This service is the gatekeeper: nothing gets marked `verified: true` unless it
passes all checks. It sets `verified: false` and appropriate `warning` entries
for anything that fails or is ambiguous. Downstream services trust the `verified`
flag without re-checking, so this must be reliable.

The output ParsedBill is aligned to the existing Vitta contract. Validation
results are attached to line items via the extension fields (`code_confidence`,
`amount_confidence`, `code_validation`, `icd10_validations`, etc.) and flags
are raised on line items for any issues found.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.models import (
    CodeValidation,
    DocumentType,
    ExtractionWarning,
    FieldConfidence,
    Flag,
    LineItem,
    ParsedBill,
    Provenance,
    Totals,
    VerificationStatus,
    WarningSeverity,
)
from app.services.reference_data import ReferenceDataService, get_reference_data_service

logger = logging.getLogger(__name__)

# Tolerance for amount reconciliation (dollars)
AMOUNT_TOL = 0.05


def reconcile_amounts(
    line_items: List[Dict[str, Any]], totals: Dict[str, Any]
) -> List[Dict[str, str]]:
    """Reconcile line-item amounts against stated totals.

    Returns a list of warning dicts with type/severity/message keys.
    Never invents missing totals — only checks what is grounded in line items.
    """
    warnings: List[Dict[str, str]] = []
    line_sum = round(
        sum(float(i.get("charge_amount") or 0) for i in line_items), 2
    )
    billed = totals.get("billed")
    if billed is not None and abs(line_sum - float(billed)) > AMOUNT_TOL:
        warnings.append(
            {
                "type": "amount_mismatch",
                "severity": "critical",
                "message": (
                    f"Line-item charge sum {line_sum} != totals.billed {billed}"
                ),
            }
        )

    for i, item in enumerate(line_items):
        allowed = item.get("allowed_amount")
        paid = item.get("paid_amount")
        pr = item.get("patient_responsibility")
        if allowed is not None and paid is not None and pr is not None:
            expected_pr = round(float(allowed) - float(paid), 2)
            if abs(expected_pr - float(pr)) > AMOUNT_TOL:
                warnings.append(
                    {
                        "type": "line_reconciliation",
                        "severity": "warning",
                        "message": (
                            f"Line {item.get('id', i)} patient_responsibility {pr} "
                            f"!= allowed-paid {expected_pr}"
                        ),
                    }
                )
    return warnings


class ValidationService:
    """Validates codes against reference data and reconciles amounts."""

    def __init__(
        self,
        reference_data: Optional[ReferenceDataService] = None,
        amount_tolerance: Optional[float] = None,
    ):
        self.ref_data = reference_data or get_reference_data_service()
        self.amount_tolerance = amount_tolerance or settings.amount_tolerance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def validate(self, draft: ParsedBill) -> ParsedBill:
        """Validate a draft ParsedBill, setting verified flags and warnings.

        Mutates the draft and returns it. Raises nothing — validation failures
        are recorded in warnings and verification_status fields.
        """
        bill = draft.model_copy(deep=True)

        warnings: List[ExtractionWarning] = list(bill.warnings)

        # Validate each line item
        for line in bill.line_items:
            self._validate_line(line, warnings)

        # Validate totals (if present) and reconcile against line items
        self._validate_totals(bill.totals, bill.line_items, warnings)

        bill.warnings = warnings
        return bill

    # ------------------------------------------------------------------
    # Line-item validation
    # ------------------------------------------------------------------
    def _validate_line(
        self, line: LineItem, warnings: List[ExtractionWarning]
    ) -> None:
        """Validate codes and amounts for a single line item."""
        # 1. CPT/HCPCS code validation
        self._validate_cpt_hcpcs(line, warnings)

        # 2. ICD-10 code validation
        self._validate_icd10(line, warnings)

        # 3. Modifier validation
        self._validate_modifiers(line, warnings)

        # 4. Amount reconciliation
        self._validate_line_amounts(line, warnings)

    def _validate_cpt_hcpcs(
        self, line: LineItem, warnings: List[ExtractionWarning]
    ) -> None:
        code = (line.cpt_hcpcs or "").strip().upper()
        confidence = line.code_confidence

        if not code:
            # No code present — flag as unverified
            if confidence is not None:
                confidence.verified = False
                confidence.verification_status = VerificationStatus.UNVERIFIED
            self._add_warning(
                warnings,
                code="MISSING_CODE",
                severity=WarningSeverity.MEDIUM,
                message=f"Line {line.id} has no CPT/HCPCS code",
                field="cpt_hcpcs",
            )
            return

        if not ReferenceDataService.looks_like_cpt(code):
            # Malformed code — not even the right format
            line.code_validation = CodeValidation(
                code=code,
                code_type="cpt_hcpcs",
                status=VerificationStatus.INVALID,
                matched_against="bundle",
                notes=["Code is not in a valid CPT/HCPCS format"],
            )
            if confidence is not None:
                self._mark_unverified(
                    confidence,
                    "cpt_hcpcs",
                    f"CPT/HCPCS code '{code}' is not in a valid format",
                    line.id,
                    warnings,
                    severity=WarningSeverity.HIGH,
                )
            return

        record = self.ref_data.lookup_cpt_hcpcs(code)

        if record is None:
            # Code not found — could be valid but not in our reference dataset
            # (e.g. a less common code). Flag as unverified/ambiguous, not invalid.
            status = VerificationStatus.AMBIGUOUS
            line.code_validation = CodeValidation(
                code=code,
                code_type="cpt_hcpcs",
                status=status,
                matched_against="bundle",
                notes=["Code not found in reference dataset — requires manual verification"],
            )
            if confidence is not None:
                self._mark_unverified(
                    confidence,
                    "cpt_hcpcs",
                    f"CPT/HCPCS code '{code}' not found in reference data",
                    line.id,
                    warnings,
                    severity=WarningSeverity.MEDIUM,
                )
            return

        if record.is_deprecated:
            status = VerificationStatus.INVALID
            line.code_validation = CodeValidation(
                code=code,
                code_type="cpt_hcpcs",
                status=status,
                description=record.description,
                is_deprecated=True,
                is_active=False,
                matched_against=record.source,
                notes=["Code is deprecated/retired"],
            )
            if confidence is not None:
                self._mark_unverified(
                    confidence,
                    "cpt_hcpcs",
                    f"CPT/HCPCS code '{code}' is deprecated/retired: {record.description}",
                    line.id,
                    warnings,
                    severity=WarningSeverity.HIGH,
                )
            return

        # Valid code
        line.code_validation = CodeValidation(
            code=code,
            code_type="cpt_hcpcs",
            status=VerificationStatus.VERIFIED,
            description=record.description,
            is_active=True,
            is_deprecated=False,
            matched_against=record.source,
            notes=["Code verified against reference dataset"],
        )
        if confidence is not None:
            confidence.verified = True
            confidence.verification_status = VerificationStatus.VERIFIED
        if not line.description:
            line.description = record.description

    def _validate_icd10(
        self, line: LineItem, warnings: List[ExtractionWarning]
    ) -> None:
        line.icd10_validations = []
        for icd in line.icd10:
            code = icd.strip().upper()
            record = self.ref_data.lookup_icd10(code)

            if record is None:
                status = VerificationStatus.AMBIGUOUS if ReferenceDataService.looks_like_icd10(code) else VerificationStatus.INVALID
                line.icd10_validations.append(
                    CodeValidation(
                        code=code,
                        code_type="icd10",
                        status=status,
                        matched_against="bundle",
                        notes=["ICD-10 code not found in reference dataset"],
                    )
                )
                if line.icd10_confidence is not None:
                    self._mark_unverified(
                        line.icd10_confidence,
                        "icd10",
                        f"ICD-10 code '{code}' failed validation ({status.value})",
                        line.id,
                        warnings,
                        severity=WarningSeverity.MEDIUM,
                    )
            else:
                status = (
                    VerificationStatus.INVALID
                    if record.is_deprecated
                    else VerificationStatus.VERIFIED
                )
                line.icd10_validations.append(
                    CodeValidation(
                        code=code,
                        code_type="icd10",
                        status=status,
                        description=record.description,
                        is_active=record.is_active,
                        is_deprecated=record.is_deprecated,
                        matched_against=record.source,
                        notes=(
                            ["ICD-10 code is deprecated/retired"]
                            if record.is_deprecated
                            else ["ICD-10 code verified against reference dataset"]
                        ),
                    )
                )
                if line.icd10_confidence is not None:
                    line.icd10_confidence.verified = status == VerificationStatus.VERIFIED
                    line.icd10_confidence.verification_status = status

    def _validate_modifiers(
        self, line: LineItem, warnings: List[ExtractionWarning]
    ) -> None:
        line.modifier_validations = []
        for mod in line.modifiers:
            code = mod.strip().upper()
            record = self.ref_data.lookup_modifier(code)

            if record is None:
                status = (
                    VerificationStatus.AMBIGUOUS
                    if len(code) in (2, 5) and code.isalnum()
                    else VerificationStatus.INVALID
                )
                line.modifier_validations.append(
                    CodeValidation(
                        code=code,
                        code_type="modifier",
                        status=status,
                        matched_against="bundle",
                        notes=["Modifier not found in reference dataset"],
                    )
                )
                if line.code_confidence is not None:
                    self._mark_unverified(
                        line.code_confidence,
                        "modifiers",
                        f"Modifier '{code}' failed validation ({status.value})",
                        line.id,
                        warnings,
                        severity=WarningSeverity.LOW,
                    )
            else:
                line.modifier_validations.append(
                    CodeValidation(
                        code=code,
                        code_type="modifier",
                        status=VerificationStatus.VERIFIED,
                        description=record.description,
                        matched_against=record.source,
                        notes=["Modifier verified against reference dataset"],
                    )
                )

    def _validate_line_amounts(
        self, line: LineItem, warnings: List[ExtractionWarning]
    ) -> None:
        """Verify: charge - allowed = adjustment, and allowed - paid = patient responsibility."""
        amounts = {
            "charge_amount": line.charge_amount,
            "allowed_amount": line.allowed_amount,
            "paid_amount": line.paid_amount,
            "patient_responsibility": line.patient_responsibility,
        }

        # If any amount is missing, we can't fully reconcile
        missing = [k for k, v in amounts.items() if v is None]
        if missing:
            if line.amount_confidence is not None:
                line.amount_confidence.verified = False
                line.amount_confidence.verification_status = VerificationStatus.UNVERIFIED
            self._add_warning(
                warnings,
                code="MISSING_AMOUNT",
                severity=WarningSeverity.MEDIUM,
                message=f"Missing amount field(s) on line {line.id}: {', '.join(missing)}",
                field="amounts",
            )
            return

        charge = line.charge_amount
        allowed = line.allowed_amount
        paid = line.paid_amount
        patient_resp = line.patient_responsibility

        all_ok = True

        # charge - allowed = adjustment (implied; patient responsibility from insurance perspective)
        # allowed - paid = patient responsibility (when patient owes the difference)
        # Key check: allowed - paid should equal patient_responsibility
        expected_patient_resp = round(allowed - paid, 2)
        patient_resp_ok = abs(expected_patient_resp - patient_resp) <= self.amount_tolerance

        # charge should be >= allowed (rare exceptions exist, but flag)
        charge_ge_allowed = charge >= allowed - self.amount_tolerance

        all_ok = patient_resp_ok and charge_ge_allowed

        line.reconciliation = {
            "allowed_minus_paid": expected_patient_resp,
            "matches_patient_responsibility": patient_resp_ok,
            "charge_ge_allowed": charge_ge_allowed,
            "all_ok": all_ok,
        }

        if all_ok:
            if line.amount_confidence is not None:
                line.amount_confidence.verified = True
                line.amount_confidence.verification_status = VerificationStatus.VERIFIED
        else:
            if line.amount_confidence is not None:
                line.amount_confidence.verified = False
                line.amount_confidence.verification_status = VerificationStatus.UNVERIFIED
            problems = []
            if not patient_resp_ok:
                problems.append(
                    f"allowed ({allowed}) - paid ({paid}) = {expected_patient_resp} "
                    f"but patient responsibility is {patient_resp}"
                )
            if not charge_ge_allowed:
                problems.append(f"charge ({charge}) is less than allowed ({allowed})")
            self._add_warning(
                warnings,
                code="AMOUNT_MISMATCH",
                severity=WarningSeverity.HIGH,
                message=f"Line {line.id} amount reconciliation failed: {'; '.join(problems)}",
                field="amounts",
            )
            # Also raise a flag on the line item (Vitta contract)
            line.flags.append(
                Flag(
                    type="amount_mismatch",
                    severity="critical",
                    message=f"Amount reconciliation failed: {'; '.join(problems)}",
                    rule_id="RULE-RECON-001",
                )
            )

    # ------------------------------------------------------------------
    # Totals validation
    # ------------------------------------------------------------------
    def _validate_totals(
        self,
        totals: Totals,
        line_items: List[LineItem],
        warnings: List[ExtractionWarning],
    ) -> None:
        """Verify totals: billed - adjustments - paid = patient_responsibility,
        and that line-item sums match stated totals."""
        issues = []

        # Check totals internal consistency
        if (
            totals.billed is not None
            and totals.allowed is not None
            and totals.insurance_paid is not None
            and totals.patient_responsibility is not None
        ):
            adjustments = totals.billed - totals.allowed
            expected = round(totals.billed - adjustments - totals.insurance_paid, 2)
            ok = abs(expected - totals.patient_responsibility) <= self.amount_tolerance
            totals.reconciliation = {
                "billed_minus_adjustments_minus_paid": expected,
                "matches_patient_responsibility": ok,
            }
            if not ok:
                issues.append(
                    f"billed ({totals.billed}) - adjustments ({adjustments}) "
                    f"- paid ({totals.insurance_paid}) = {expected}, but stated patient "
                    f"responsibility is {totals.patient_responsibility}"
                )
                self._add_warning(
                    warnings,
                    code="TOTALS_MISMATCH",
                    severity=WarningSeverity.HIGH,
                    message=f"Totals reconciliation failed: {issues[-1]}",
                    field="totals",
                )

        # Check line-item sums against stated totals where both are available
        self._check_line_sum(
            "billed",
            line_items,
            lambda li: li.charge_amount,
            totals.billed,
            warnings,
        )
        self._check_line_sum(
            "allowed",
            line_items,
            lambda li: li.allowed_amount,
            totals.allowed,
            warnings,
        )
        self._check_line_sum(
            "insurance_paid",
            line_items,
            lambda li: li.paid_amount,
            totals.insurance_paid,
            warnings,
        )
        self._check_line_sum(
            "patient_responsibility",
            line_items,
            lambda li: li.patient_responsibility,
            totals.patient_responsibility,
            warnings,
        )

        # If issues exist, totals are unverified
        if issues:
            logger.info("Totals validation issues: %s", issues)

    def _check_line_sum(
        self,
        field_name: str,
        line_items: List[LineItem],
        getter,
        stated_total: Optional[float],
        warnings: List[ExtractionWarning],
    ) -> None:
        if stated_total is None:
            return
        values = []
        for li in line_items:
            v = getter(li)
            if v is not None:
                values.append(v)
        if not values:
            return
        computed = round(sum(values), 2)
        if abs(computed - stated_total) > self.amount_tolerance:
            self._add_warning(
                warnings,
                code="TOTALS_VS_LINES_MISMATCH",
                severity=WarningSeverity.HIGH,
                message=(
                    f"Stated {field_name} ({stated_total}) does not match the sum "
                    f"of line items ({computed})"
                ),
                field="totals",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _mark_unverified(
        self,
        confidence: FieldConfidence,
        field: str,
        reason: str,
        line_id: Optional[str],
        warnings: List[ExtractionWarning],
        severity: WarningSeverity = WarningSeverity.MEDIUM,
    ) -> None:
        confidence.verified = False
        if confidence.verification_status == VerificationStatus.VERIFIED:
            confidence.verification_status = VerificationStatus.UNVERIFIED
        self._add_warning(
            warnings,
            code="VERIFICATION_FAILED",
            severity=severity,
            message=reason,
            field=field,
        )

    def _add_warning(
        self,
        warnings: List[ExtractionWarning],
        code: str,
        severity: WarningSeverity,
        message: str,
        field: Optional[str] = None,
        line_number: Optional[int] = None,
        page: Optional[int] = None,
        provenance: Optional[Provenance] = None,
    ) -> None:
        warnings.append(
            ExtractionWarning(
                code=code,
                severity=severity,
                message=message,
                field=field,
                line_number=line_number,
                page=page,
                provenance=provenance,
            )
        )


def get_validation_service() -> ValidationService:
    return ValidationService()