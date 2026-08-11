from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime
from enum import Enum


class DocumentStatus(str, Enum):
    uploaded = "uploaded"
    processing = "processing"
    analyzed = "analyzed"
    letter_ready = "letter_ready"
    error = "error"


class Flag(BaseModel):
    type: str
    severity: str  # "info" | "warning" | "critical"
    message: str
    rule_id: Optional[str] = None
    shap_contribution: Optional[float] = None


class LineItem(BaseModel):
    id: str
    page: int = 1
    description: str
    cpt_hcpcs: Optional[str] = None
    icd10: List[str] = []
    units: float = 1.0
    charge_amount: float
    allowed_amount: Optional[float] = None
    paid_amount: Optional[float] = None
    patient_responsibility: Optional[float] = None
    modifiers: List[str] = []
    flags: List[Flag] = []


class Totals(BaseModel):
    billed: float
    allowed: Optional[float] = None
    insurance_paid: Optional[float] = None
    patient_responsibility: Optional[float] = None
    potential_savings: Optional[float] = None


class AppealPrediction(BaseModel):
    success_probability: float
    confidence_interval: List[float]
    top_factors: List[str] = []


class Letter(BaseModel):
    status: str = "draft"  # "draft" | "verified" | "sent"
    content_markdown: str
    verified_fields: List[str] = []


class ParsedBill(BaseModel):
    document_id: str
    status: DocumentStatus
    uploaded_at: datetime
    source_type: str
    patient: dict = {}
    provider: dict = {}
    payer: dict = {}
    service_date: Optional[date] = None
    line_items: List[LineItem] = []
    totals: Totals
    denial_codes: List[dict] = []
    appeal_prediction: Optional[AppealPrediction] = None
    explanation: Optional[str] = None
    letter: Optional[Letter] = None
    audit: dict = {}


# ---------- API request/response schemas ----------

class DocumentCreate(BaseModel):
    original_filename: str
    storage_key: str
    content_type: str


class DocumentResponse(BaseModel):
    id: str
    original_filename: str
    storage_key: str
    content_type: str
    status: DocumentStatus
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DocumentStatusResponse(BaseModel):
    id: str
    status: DocumentStatus
    error_message: Optional[str] = None
    updated_at: datetime


class DocumentDetailResponse(DocumentResponse):
    result: Optional[ParsedBill] = None


class HealthResponse(BaseModel):
    status: str
    environment: str
    version: str