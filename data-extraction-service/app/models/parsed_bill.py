"""ParsedBill — the shared contract for the entire medical bill/EOB analysis platform.

This is the single source of truth that downstream services (Rust rules engine,
grounded LLM letter generator) trust without re-checking. Every extracted value
carries provenance (where it came from) and a verified flag. Nothing is silently
passed through unverified — low-confidence or unverified values are flagged
explicitly.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class DocumentType(str, Enum):
    BILL = "bill"
    EOB = "eob"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


class WarningSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlaceOfService(str, Enum):
    OFFICE = "11"
    HOME = "12"
    OUTPATIENT_HOSPITAL = "22"
    EMERGENCY_ROOM = "23"
    INPATIENT_HOSPITAL = "21"
    AMBULATORY_SURGICAL = "24"
    UNKNOWN = "99"


# ---------------------------------------------------------------------------
# Provenance & confidence
# ---------------------------------------------------------------------------
class Provenance(BaseModel):
    """Pointer back to the source location of an extracted value."""

    page: int = Field(..., description="1-based page number in the source document")
    bounding_box: Optional[List[float]] = Field(
        default=None,
        description="Normalized [x1, y1, x2, y2] bounding box (0-1 coordinates)",
    )
    text: Optional[str] = Field(
        default=None, description="The raw source text this value was extracted from"
    )
    table_id: Optional[str] = Field(
        default=None, description="Identifier of the source table, if from a table"
    )
    row_index: Optional[int] = Field(
        default=None, description="0-based row index within the source table"
    )
    column_index: Optional[int] = Field(
        default=None, description="0-based column index within the source table"
    )


class FieldConfidence(BaseModel):
    """Per-field confidence and verification status."""

    ocr_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="OCR confidence score (0-1)"
    )
    extraction_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Extraction model confidence (0-1)"
    )
    verified: bool = Field(
        default=False,
        description="True only if the value passed all validation checks",
    )
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.UNVERIFIED,
        description="Detailed verification status",
    )
    provenance: Optional[Provenance] = Field(
        default=None, description="Source location of this value"
    )


# ---------------------------------------------------------------------------
# Code validation
# ---------------------------------------------------------------------------
class CodeValidation(BaseModel):
    """Result of validating a code against CMS/AMA reference data."""

    code: str = Field(..., description="The code that was validated")
    code_type: str = Field(
        ..., description="One of: cpt, hcpcs, icd10, modifier"
    )
    status: VerificationStatus = Field(
        ..., description="verified / unverified / ambiguous / invalid"
    )
    description: Optional[str] = Field(
        default=None, description="Canonical description from the reference dataset"
    )
    is_deprecated: bool = Field(
        default=False, description="True if the code is deprecated/retired"
    )
    is_active: bool = Field(
        default=True, description="True if the code is currently active"
    )
    matched_against: str = Field(
        ..., description="Reference dataset used (e.g. 'cms_cpt_2024', 'ama_cpt_2024')"
    )
    notes: Optional[List[str]] = Field(
        default=None, description="Human-readable notes about the validation result"
    )


# ---------------------------------------------------------------------------
# Line item
# ---------------------------------------------------------------------------
class LineItem(BaseModel):
    """A single line item from a bill or EOB."""

    line_number: int = Field(..., description="1-based line number within the document")

    # Codes
    cpt_hcpcs_code: str = Field(..., description="CPT or HCPCS procedure code")
    code_description: Optional[str] = Field(
        default=None, description="Description of the procedure code"
    )
    icd10_codes: List[str] = Field(
        default_factory=list, description="ICD-10 diagnosis code(s) for this line"
    )
    modifier_codes: List[str] = Field(
        default_factory=list, description="CPT modifier code(s), e.g. ['25', '59']"
    )

    # Service details
    units: float = Field(default=1.0, ge=0.0, description="Number of units billed")
    date_of_service: Optional[date] = Field(
        default=None, description="Date of service for this line"
    )
    place_of_service: PlaceOfService = Field(
        default=PlaceOfService.UNKNOWN, description="Place of service code"
    )

    # Amounts (in dollars)
    charge_amount: Optional[float] = Field(
        default=None, ge=0.0, description="Amount charged by the provider"
    )
    allowed_amount: Optional[float] = Field(
        default=None, ge=0.0, description="Amount allowed by the payer"
    )
    paid_amount: Optional[float] = Field(
        default=None, ge=0.0, description="Amount paid by the payer"
    )
    patient_responsibility: Optional[float] = Field(
        default=None, ge=0.0, description="Amount the patient owes for this line"
    )

    # Per-field confidence & provenance
    code_confidence: FieldConfidence = Field(
        ..., description="Confidence/verification for the CPT/HCPCS code"
    )
    amount_confidence: FieldConfidence = Field(
        ..., description="Confidence/verification for the amounts on this line"
    )
    icd10_confidence: Optional[FieldConfidence] = Field(
        default=None, description="Confidence/verification for ICD-10 codes"
    )

    # Validation results
    code_validation: Optional[CodeValidation] = Field(
        default=None, description="Result of validating the CPT/HCPCS code"
    )
    icd10_validations: List[CodeValidation] = Field(
        default_factory=list, description="Results of validating each ICD-10 code"
    )
    modifier_validations: List[CodeValidation] = Field(
        default_factory=list, description="Results of validating each modifier"
    )

    # Reconciliation check
    reconciliation: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Result of amount reconciliation for this line, e.g. "
        "{'charge_minus_allowed': 50.0, 'allowed_minus_paid': 20.0, "
        "'matches_patient_responsibility': true}",
    )

    @model_validator(mode="after")
    def validate_line_reconciliation(self) -> "LineItem":
        """Check that charge - allowed = adjustment and allowed - paid = patient responsibility."""
        if (
            self.charge_amount is not None
            and self.allowed_amount is not None
            and self.paid_amount is not None
            and self.patient_responsibility is not None
        ):
            adjustment = round(self.charge_amount - self.allowed_amount, 2)
            patient_resp_from_recon = round(self.allowed_amount - self.paid_amount, 2)
            matches = abs(patient_resp_from_recon - self.patient_responsibility) < 0.01
            self.reconciliation = {
                "charge_minus_allowed": adjustment,
                "allowed_minus_paid": patient_resp_from_recon,
                "matches_patient_responsibility": matches,
            }
        return self


# ---------------------------------------------------------------------------
# Totals block
# ---------------------------------------------------------------------------
class TotalsBlock(BaseModel):
    """Document-level totals. Must satisfy: billed - adjustments - paid = patient_responsibility."""

    billed_total: Optional[float] = Field(
        default=None, ge=0.0, description="Total amount billed"
    )
    allowed_total: Optional[float] = Field(
        default=None, ge=0.0, description="Total amount allowed"
    )
    paid_total: Optional[float] = Field(
        default=None, ge=0.0, description="Total amount paid"
    )
    patient_responsibility_total: Optional[float] = Field(
        default=None, ge=0.0, description="Total patient responsibility"
    )
    adjustments_total: Optional[float] = Field(
        default=None, ge=0.0, description="Total adjustments (billed - allowed)"
    )

    # Reconciliation
    reconciliation: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Result of totals reconciliation, e.g. "
        "{'billed_minus_adjustments_minus_paid': 0.0, "
        "'matches_patient_responsibility': true}",
    )

    @model_validator(mode="after")
    def validate_totals_reconciliation(self) -> "TotalsBlock":
        """Verify billed - adjustments - paid = patient_responsibility."""
        if (
            self.billed_total is not None
            and self.adjustments_total is not None
            and self.paid_total is not None
            and self.patient_responsibility_total is not None
        ):
            computed = round(
                self.billed_total - self.adjustments_total - self.paid_total, 2
            )
            matches = abs(computed - self.patient_responsibility_total) < 0.01
            self.reconciliation = {
                "billed_minus_adjustments_minus_paid": computed,
                "matches_patient_responsibility": matches,
            }
        return self


# ---------------------------------------------------------------------------
# Pricing anomaly & appeal success
# ---------------------------------------------------------------------------
class ShapExplanation(BaseModel):
    """A single human-readable SHAP feature contribution, pre-formatted for an LLM."""

    feature: str = Field(..., description="Feature name, e.g. 'charge_amount'")
    contribution: float = Field(
        ..., description="SHAP contribution value (in log-odds or probability space)"
    )
    direction: str = Field(
        ..., description="One of: 'increases_anomaly', 'decreases_anomaly'"
    )
    human_readable: str = Field(
        ...,
        description="Pre-formatted human-readable explanation, e.g. "
        "'charge is 3.2x the regional median for CPT 99214'",
    )


class PricingAnomaly(BaseModel):
    """Pricing anomaly score and explanation."""

    score: float = Field(
        ..., ge=0.0, le=1.0, description="Anomaly score (0 = normal, 1 = highly anomalous)"
    )
    calibrated_probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Calibrated probability that this charge is anomalous",
    )
    is_anomalous: bool = Field(
        default=False, description="True if the score exceeds the anomaly threshold"
    )
    threshold: float = Field(
        default=0.7, description="Threshold used to determine is_anomalous"
    )
    explanation: List[ShapExplanation] = Field(
        default_factory=list,
        description="Structured SHAP-style feature contributions, pre-formatted for LLM",
    )


class AppealSuccess(BaseModel):
    """Appeal-success probability and explanation."""

    score: float = Field(
        ..., ge=0.0, le=1.0, description="Appeal-success score (0-1)"
    )
    calibrated_probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Calibrated probability of appeal success",
    )
    recommendation: str = Field(
        ...,
        description="One of: 'strong_appeal', 'moderate_appeal', 'weak_appeal', 'no_appeal'",
    )
    explanation: List[ShapExplanation] = Field(
        default_factory=list,
        description="Structured SHAP-style feature contributions, pre-formatted for LLM",
    )


# ---------------------------------------------------------------------------
# Extraction warnings
# ---------------------------------------------------------------------------
class ExtractionWarning(BaseModel):
    """A warning about a low-confidence field, illegible region, or missing field."""

    code: str = Field(..., description="Machine-readable warning code, e.g. 'LOW_CONF'")
    severity: WarningSeverity = Field(..., description="Warning severity")
    message: str = Field(..., description="Human-readable warning message")
    field: Optional[str] = Field(
        default=None, description="The field this warning applies to"
    )
    line_number: Optional[int] = Field(
        default=None, description="Line number this warning applies to, if any"
    )
    page: Optional[int] = Field(
        default=None, description="Page this warning applies to, if any"
    )
    provenance: Optional[Provenance] = Field(
        default=None, description="Source location of the issue"
    )


# ---------------------------------------------------------------------------
# Document metadata
# ---------------------------------------------------------------------------
class DocumentMetadata(BaseModel):
    """Metadata about the source document."""

    document_type: DocumentType = Field(
        ..., description="Whether this is a bill or an EOB"
    )
    provider_name: Optional[str] = Field(
        default=None, description="Name of the healthcare provider"
    )
    provider_npi: Optional[str] = Field(
        default=None, description="Provider NPI (National Provider Identifier)"
    )
    payer_name: Optional[str] = Field(
        default=None, description="Name of the insurance payer"
    )
    patient_account_ref: Optional[str] = Field(
        default=None,
        description="De-identified patient account reference (never PII)",
    )
    service_date_start: Optional[date] = Field(
        default=None, description="Start of the service date range"
    )
    service_date_end: Optional[date] = Field(
        default=None, description="End of the service date range"
    )
    statement_date: Optional[date] = Field(
        default=None, description="Date the statement was issued"
    )

    # Confidence for metadata fields
    metadata_confidence: Dict[str, FieldConfidence] = Field(
        default_factory=dict,
        description="Per-field confidence for metadata, keyed by field name",
    )


# ---------------------------------------------------------------------------
# ParsedBill — the top-level contract
# ---------------------------------------------------------------------------
class ParsedBill(BaseModel):
    """The validated, structured representation of a medical bill or EOB.

    This is the shared contract for the whole system. Downstream services trust
    the `verified` flags without re-checking, so unverified values are always
    flagged explicitly via warnings and verification_status.
    """

    schema_version: str = Field(
        default="1.0.0", description="Version of the ParsedBill schema"
    )
    document_id: str = Field(
        ..., description="Unique identifier for this parsed document"
    )
    metadata: DocumentMetadata = Field(..., description="Document metadata")
    line_items: List[LineItem] = Field(
        default_factory=list, description="Extracted line items"
    )
    totals: Optional[TotalsBlock] = Field(
        default=None, description="Document-level totals"
    )
    pricing_anomaly: Optional[PricingAnomaly] = Field(
        default=None, description="Pricing anomaly score and explanation"
    )
    appeal_success: Optional[AppealSuccess] = Field(
        default=None, description="Appeal-success probability and explanation"
    )
    warnings: List[ExtractionWarning] = Field(
        default_factory=list, description="Extraction warnings"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When this ParsedBill was created"
    )

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("document_id must not be empty")
        return v.strip()

    @model_validator(mode="after")
    def validate_metadata_confidence(self) -> "ParsedBill":
        """Ensure metadata confidence is present for all populated metadata fields."""
        if self.metadata.metadata_confidence:
            for field_name in self.metadata.metadata_confidence:
                if not hasattr(self.metadata, field_name):
                    raise ValueError(
                        f"metadata_confidence references unknown field: {field_name}"
                    )
        return self