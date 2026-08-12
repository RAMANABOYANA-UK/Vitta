"""ParsedBill — the shared contract for the entire medical bill/EOB analysis platform.

This model is aligned to the existing Vitta contract (see
`medical-bill-backend/app/schemas.py` and `bill_rules/src/types.rs`) so that the
output of this service feeds directly into the backend → Rust rules engine →
LLM letter generator pipeline.

The primary fields match the Vitta contract exactly. Richer per-field
confidence, provenance, and validation data from this service are preserved as
*extension* fields (e.g. `code_confidence`, `amount_confidence`,
`code_validation`, `pricing_anomaly`, `appeal_success`, `warnings`) so no
information is lost.

Core rule: never silently pass through an unverified or low-confidence value —
flag it explicitly. Downstream services trust the `verified` flag without
re-checking it, so it has to be reliable.
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


class DocumentStatus(str, Enum):
    uploaded = "uploaded"
    processing = "processing"
    analyzed = "analyzed"
    letter_ready = "letter_ready"
    error = "error"


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
# Provenance & confidence (extensions)
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
# Code validation (extensions)
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
# Flag — matches the Vitta contract (bill_rules/src/types.rs, schemas.py)
# ---------------------------------------------------------------------------
class Flag(BaseModel):
    """A single flagged issue on a line item or the bill as a whole."""

    type: str = Field(..., description="Flag type, e.g. 'price_inflated'")
    severity: str = Field(
        ..., description="One of: info, warning, critical, high"
    )
    message: str = Field(..., description="Human-readable message")
    rule_id: Optional[str] = Field(
        default=None, description="Identifier of the rule that produced this flag"
    )
    shap_contribution: Optional[float] = Field(
        default=None, description="SHAP contribution value, if applicable"
    )


# ---------------------------------------------------------------------------
# Line item — matches the Vitta contract + extensions
# ---------------------------------------------------------------------------
class LineItem(BaseModel):
    """A single line item on a medical bill / EOB.

    Primary fields match the Vitta contract. Extension fields (confidence,
    validation, reconciliation) carry this service's richer data.
    """

    id: str = Field(..., description="Unique line item identifier")
    page: int = Field(default=1, description="Page number in the source document")
    description: str = Field(default="", description="Description of the service")
    cpt_hcpcs: Optional[str] = Field(
        default=None, description="CPT or HCPCS procedure code"
    )
    icd10: List[str] = Field(
        default_factory=list, description="ICD-10 diagnosis code(s)"
    )
    units: float = Field(default=1.0, ge=0.0, description="Number of units billed")
    charge_amount: float = Field(
        default=0.0, ge=0.0, description="Amount charged by the provider"
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
    modifiers: List[str] = Field(
        default_factory=list, description="CPT modifier code(s)"
    )
    flags: List[Flag] = Field(
        default_factory=list, description="Flags raised on this line item"
    )

    # --- Extensions (this service's richer data) ---
    code_confidence: Optional[FieldConfidence] = Field(
        default=None, description="Confidence/verification for the CPT/HCPCS code"
    )
    amount_confidence: Optional[FieldConfidence] = Field(
        default=None, description="Confidence/verification for the amounts"
    )
    icd10_confidence: Optional[FieldConfidence] = Field(
        default=None, description="Confidence/verification for ICD-10 codes"
    )
    code_validation: Optional[CodeValidation] = Field(
        default=None, description="Result of validating the CPT/HCPCS code"
    )
    icd10_validations: List[CodeValidation] = Field(
        default_factory=list, description="Results of validating each ICD-10 code"
    )
    modifier_validations: List[CodeValidation] = Field(
        default_factory=list, description="Results of validating each modifier"
    )
    reconciliation: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Result of amount reconciliation for this line",
    )


# ---------------------------------------------------------------------------
# Totals — matches the Vitta contract + extensions
# ---------------------------------------------------------------------------
class Totals(BaseModel):
    """Aggregated totals for the bill.

    Primary fields match the Vitta contract. Extension fields carry this
    service's reconciliation data.
    """

    billed: float = Field(default=0.0, ge=0.0, description="Total amount billed")
    allowed: Optional[float] = Field(
        default=None, ge=0.0, description="Total amount allowed"
    )
    insurance_paid: Optional[float] = Field(
        default=None, ge=0.0, description="Total amount paid by insurance"
    )
    patient_responsibility: Optional[float] = Field(
        default=None, ge=0.0, description="Total patient responsibility"
    )
    potential_savings: Optional[float] = Field(
        default=None, ge=0.0, description="Estimated potential savings"
    )

    # --- Extensions ---
    adjustments_total: Optional[float] = Field(
        default=None, ge=0.0, description="Total adjustments (billed - allowed)"
    )
    reconciliation: Optional[Dict[str, Any]] = Field(
        default=None, description="Result of totals reconciliation"
    )


# ---------------------------------------------------------------------------
# Pricing anomaly & appeal success (extensions)
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
# Appeal prediction — matches the Vitta contract + extensions
# ---------------------------------------------------------------------------
class AppealPrediction(BaseModel):
    """Appeal success prediction, matching the Vitta contract."""

    success_probability: float = Field(
        ..., ge=0.0, le=1.0, description="Probability of appeal success"
    )
    confidence_interval: List[float] = Field(
        default_factory=list, description="Confidence interval [low, high]"
    )
    top_factors: List[str] = Field(
        default_factory=list, description="Top factors supporting the prediction"
    )

    # --- Extensions ---
    recommendation: Optional[str] = Field(
        default=None,
        description="One of: 'strong_appeal', 'moderate_appeal', 'weak_appeal', 'no_appeal'",
    )
    explanation: List[ShapExplanation] = Field(
        default_factory=list,
        description="Structured SHAP-style feature contributions, pre-formatted for LLM",
    )


# ---------------------------------------------------------------------------
# Letter — matches the Vitta contract
# ---------------------------------------------------------------------------
class Letter(BaseModel):
    """An appeal letter, matching the Vitta contract."""

    status: str = Field(default="draft", description="draft | verified | sent")
    content_markdown: str = Field(default="", description="Letter content in markdown")
    verified_fields: List[str] = Field(
        default_factory=list, description="Fields verified before sending"
    )


# ---------------------------------------------------------------------------
# Extraction warnings (extensions)
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
# Document metadata (extensions)
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
# ParsedBill — the top-level contract (aligned to Vitta + extensions)
# ---------------------------------------------------------------------------
class ParsedBill(BaseModel):
    """The validated, structured representation of a medical bill or EOB.

    Primary fields match the existing Vitta contract so this service's output
    feeds directly into the backend → Rust rules engine → LLM letter generator
    pipeline. Extension fields carry this service's richer confidence,
    provenance, validation, and scoring data.
    """

    document_id: str = Field(..., description="Unique identifier for this document")
    status: DocumentStatus = Field(
        default=DocumentStatus.processing, description="Document processing status"
    )
    uploaded_at: datetime = Field(
        default_factory=datetime.utcnow, description="When the document was uploaded"
    )
    source_type: str = Field(
        default="ocr_extraction_v0", description="Source of the extraction"
    )
    patient: Dict[str, Any] = Field(
        default_factory=dict, description="De-identified patient information"
    )
    provider: Dict[str, Any] = Field(
        default_factory=dict, description="Provider information"
    )
    payer: Dict[str, Any] = Field(
        default_factory=dict, description="Payer information"
    )
    service_date: Optional[date] = Field(
        default=None, description="Date of service"
    )
    line_items: List[LineItem] = Field(
        default_factory=list, description="Extracted line items"
    )
    totals: Totals = Field(
        default_factory=Totals, description="Document-level totals"
    )
    denial_codes: List[Dict[str, Any]] = Field(
        default_factory=list, description="Denial codes identified"
    )
    appeal_prediction: Optional[AppealPrediction] = Field(
        default=None, description="Appeal success prediction"
    )
    explanation: Optional[str] = Field(
        default=None, description="Natural-language explanation of the analysis"
    )
    letter: Optional[Letter] = Field(
        default=None, description="Generated appeal letter"
    )
    audit: Dict[str, Any] = Field(
        default_factory=dict, description="Audit metadata"
    )

    # --- Extensions (this service's richer data) ---
    schema_version: str = Field(
        default="1.0.0", description="Version of the ParsedBill schema"
    )
    document_type: Optional[DocumentType] = Field(
        default=None, description="Whether this is a bill or an EOB"
    )
    metadata: Optional[DocumentMetadata] = Field(
        default=None, description="Document metadata (extension)"
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