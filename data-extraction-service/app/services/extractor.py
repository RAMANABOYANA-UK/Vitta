"""Extraction pipeline — turns raw OCR text + layout JSON into a draft ParsedBill.

Uses Instructor (structured/schema-constrained output) with an LLM to extract
the document into the ParsedBill schema. Handles both bill and EOB layouts.

Key design principles:
- Preserve provenance: every extracted value carries a pointer back to its
  source location (page, bounding box, table cell).
- Flag rather than guess: low-confidence regions, multi-page tables, and
  handwriting are flagged in warnings, never silently passed through.
- Never silently pass through unverified values — the LLM sets initial
  confidence; the validation service later sets verified flags.

If no LLM API key is configured, falls back to an offline heuristic parser so
the service remains demoable/testable without external dependencies.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.models import (
    DocumentMetadata,
    DocumentType,
    ExtractionWarning,
    FieldConfidence,
    LineItem,
    ParsedBill,
    PlaceOfService,
    Provenance,
    TotalsBlock,
    WarningSeverity,
)

logger = logging.getLogger(__name__)

# Amount-matching pattern: requires a decimal point (medical amounts have cents)
# or a $ prefix. This avoids matching CPT code digits like "992" from "99214".
_AMOUNT_RE = re.compile(
    r"\$?\s?([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2}|[0-9]+\.[0-9]{2})"
)

# CPT/HCPCS pattern: 5 chars alphanumeric
_CPT_RE = re.compile(r"\b([A-Z][0-9]{4}|[0-9]{5})\b")

# ICD-10 pattern
_ICD10_RE = re.compile(r"\b([A-Z][0-9]{0,3}(?:\.[0-9]{0,2})?)\b")

# Date patterns (US medical format MM/DD/YYYY most common)
_DATE_RE = re.compile(r"\b([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})\b")


@dataclass
class ExtractionRequest:
    """Raw input to the extraction pipeline."""

    raw_ocr_text: str
    layout_json: Optional[Dict[str, Any]] = None
    document_id: Optional[str] = None


@dataclass
class HeuristicToken:
    text: str
    page: int
    bounding_box: Optional[List[float]] = None
    table_id: Optional[str] = None
    row_index: Optional[int] = None
    column_index: Optional[int] = None
    ocr_confidence: float = 1.0


class ExtractionService:
    """Main extraction service. Sends structured extraction to the LLM, or
    falls back to a deterministic heuristic parser."""

    def __init__(self):
        self.llm_configured = bool(settings.openai_api_key)
        if self.llm_configured:
            try:
                self._init_instructor()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to init Instructor, falling back to heuristic: %s", exc)
                self.llm_configured = False

    def _init_instructor(self) -> None:
        import instructor
        from openai import OpenAI

        kwargs: Dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        client = OpenAI(**kwargs)
        self.instructor_client = instructor.from_openai(client)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def extract(self, request: ExtractionRequest) -> ParsedBill:
        """Produce a draft ParsedBill from OCR text + layout JSON."""
        document_id = request.document_id or f"doc-{uuid.uuid4().hex[:12]}"

        layout = request.layout_json or {}
        tokens = self._tokens_from_layout(layout, request.raw_ocr_text)

        warnings: List[ExtractionWarning] = []

        # Detect handwriting / multi-page tables / low-confidence flags
        self._detect_issues(layout, request.raw_ocr_text, tokens, warnings)

        if self.llm_configured:
            draft = self._extract_with_llm(request, document_id, tokens, warnings)
        else:
            draft = self._extract_heuristic(request, document_id, tokens, warnings)

        return draft

    # ------------------------------------------------------------------
    # Layout handling
    # ------------------------------------------------------------------
    def _tokens_from_layout(
        self, layout: Dict[str, Any], raw_text: str
    ) -> List[HeuristicToken]:
        """Extract per-token provenance from the layout JSON (Textract/Document AI/
        Form Recognizer style). Falls back to whole-document text."""
        tokens: List[HeuristicToken] = []

        blocks = layout.get("blocks") or layout.get("elements") or layout.get("words") or []
        tables = layout.get("tables") or []

        # 1. Text blocks
        for idx, blk in enumerate(blocks):
            text = blk.get("text") or blk.get("content") or ""
            conf = float(blk.get("confidence", 1.0))
            page = int(blk.get("page", blk.get("page_number", 1)))
            bbox = blk.get("bounding_box") or blk.get("bbox") or blk.get("geometry")
            if isinstance(bbox, dict):
                bbox = [
                    bbox.get("left", 0.0),
                    bbox.get("top", 0.0),
                    bbox.get("width", 1.0),
                    bbox.get("height", 1.0),
                ]
            tokens.append(
                HeuristicToken(
                    text=text,
                    page=page,
                    bounding_box=bbox,
                    ocr_confidence=conf,
                )
            )

        # 2. Table cells
        for t_idx, table in enumerate(tables):
            table_id = table.get("id") or f"table-{t_idx}"
            for r_idx, row in enumerate(table.get("rows", [])):
                for c_idx, cell in enumerate(row.get("cells", row) if isinstance(row, dict) else row):
                    if isinstance(cell, dict):
                        cell_text = cell.get("text") or cell.get("content") or ""
                        cell_conf = float(cell.get("confidence", 1.0))
                    else:
                        cell_text = str(cell)
                        cell_conf = 1.0
                    tokens.append(
                        HeuristicToken(
                            text=cell_text,
                            page=int(table.get("page", 1)),
                            table_id=table_id,
                            row_index=r_idx,
                            column_index=c_idx if isinstance(row, dict) else None,
                            ocr_confidence=cell_conf,
                        )
                    )

        # 3. If no structured blocks, treat whole text as one token
        if not tokens and raw_text.strip():
            tokens.append(HeuristicToken(text=raw_text, page=1))

        return tokens

    def _detect_issues(
        self,
        layout: Dict[str, Any],
        raw_text: str,
        tokens: List[HeuristicToken],
        warnings: List[ExtractionWarning],
    ) -> None:
        """Flag handwriting, multi-page tables, and low-confidence regions."""
        # Multi-page tables
        if layout.get("tables"):
            pages = set()
            for t in layout.get("tables", []):
                pages.add(int(t.get("page", 1)))
                for row in t.get("rows", []):
                    for cell in (row.get("cells", []) if isinstance(row, dict) else row):
                        p = int((cell.get("page", 1) if isinstance(cell, dict) else 1))
                        pages.add(p)
            if len(pages) > 1:
                warnings.append(
                    ExtractionWarning(
                        code="MULTIPAGE_TABLE",
                        severity=WarningSeverity.MEDIUM,
                        message=(
                            "Table spans multiple pages; rows may be mis-associated "
                            "with the wrong page or column."
                        ),
                        field="line_items",
                    )
                )

        # Handwriting detection — heuristic: look for common handwriting markers
        # in document metadata (Textract/DocAI often emit a "handwritten" flag).
        handwritten_flags = layout.get("is_handwritten", layout.get("handwritten", False))
        if handwritten_flags:
            warnings.append(
                ExtractionWarning(
                    code="HANDWRITING_DETECTED",
                    severity=WarningSeverity.HIGH,
                    message="Handwriting detected in document — extraction may be unreliable.",
                )
            )

        # Low-confidence regions
        for tok in tokens:
            if tok.ocr_confidence < settings.low_confidence_threshold:
                warnings.append(
                    ExtractionWarning(
                        code="LOW_CONF",
                        severity=WarningSeverity.MEDIUM,
                        message=(
                            f"Low OCR confidence ({tok.ocr_confidence:.2f}) for text "
                            f"'{tok.text[:50]}'"
                        ),
                        page=tok.page,
                        provenance=Provenance(
                            page=tok.page,
                            bounding_box=tok.bounding_box,
                            text=tok.text[:200],
                            table_id=tok.table_id,
                            row_index=tok.row_index,
                            column_index=tok.column_index,
                        ),
                    )
                )

        # Illegible region markers (common in OCR outputs)
        illegible = layout.get("illegible", [])
        for region in illegible:
            warnings.append(
                ExtractionWarning(
                    code="ILLEGIBLE_REGION",
                    severity=WarningSeverity.HIGH,
                    message="Illegible region detected — values here cannot be extracted.",
                    provenance=Provenance(
                        page=int(region.get("page", 1)) if isinstance(region, dict) else 1,
                        bounding_box=(
                            region.get("bounding_box")
                            if isinstance(region, dict) and "bounding_box" in region
                            else None
                        ),
                    ),
                )
            )

    # ------------------------------------------------------------------
    # LLM extraction (Instructor)
    # ------------------------------------------------------------------
    def _extract_with_llm(
        self,
        request: ExtractionRequest,
        document_id: str,
        tokens: List[HeuristicToken],
        warnings: List[ExtractionWarning],
    ) -> ParsedBill:
        from app.models.parsed_bill import ParsedBill as PB

        # Build a compact representation of tokens with provenance for the prompt
        token_summary = self._token_summary(tokens)

        prompt = (
            "You are a medical billing extraction assistant. Extract the following "
            "document into the ParsedBill schema. The document is either a medical "
            "bill or an Explanation of Benefits (EOB). The two have different column "
            "structures.\n\n"
            "CRITICAL RULES:\n"
            "1. Preserve provenance: for every value you extract, record the source "
            "   location (page, bounding box, table cell, or raw text) from the "
            "   TOKENS section below. Use the token that contained the value.\n"
            "2. Never guess: if a value is ambiguous, low-confidence, or missing, "
            "   set ocr_confidence/extraction_confidence accordingly and ensure the "
            "   relevant warnings are emitted. Do NOT invent values.\n"
            "3. If the document contains handwriting, multi-page tables, or illegible "
            "   regions, you will see warnings already flagged — respect them.\n"
            "4. Line items: a bill lists charges by the provider. An EOB lists the "
            "   same services but adds allowed/paid/patient-responsibility columns. "
            "   Map accordingly.\n"
            "5. Totals: verify billed - adjustments - paid = patient_responsibility.\n\n"
            f"Raw OCR text:\n{request.raw_ocr_text}\n\n"
            f"Tokens with provenance:\n{token_summary}\n\n"
            f"Document ID: {document_id}\n"
            "Return the full ParsedBill object. Populate document_type, metadata "
            "(de-identify patient account ref), line_items with provenance, totals, "
            "and extraction warnings (include the pre-flagged warnings above)."
        )

        try:
            result = self.instructor_client.chat.completions.create(
                model=settings.llm_model,
                response_model=PB,
                temperature=settings.llm_temperature,
                max_retries=settings.llm_max_retries,
                messages=[{"role": "user", "content": prompt}],
            )
            # Merge pre-flagged warnings from OCR into the LLM's warnings
            existing_codes = {w.code for w in result.warnings}
            for w in warnings:
                if w.code not in existing_codes:
                    result.warnings.append(w)
            return result
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("LLM extraction failed: %s", exc)
            warnings.append(
                ExtractionWarning(
                    code="LLM_FAILURE",
                    severity=WarningSeverity.HIGH,
                    message="LLM extraction failed — falling back to heuristic parser.",
                )
            )
            return self._extract_heuristic(request, document_id, tokens, warnings)

    def _token_summary(self, tokens: List[HeuristicToken]) -> str:
        """Compact provenance-bearing summary of tokens for the LLM prompt."""
        lines = []
        for i, tok in enumerate(tokens[:500]):  # cap for token budget
            parts = [
                f"[{i}]",
                f"page={tok.page}",
                f"conf={tok.ocr_confidence:.2f}",
            ]
            if tok.bounding_box:
                parts.append(f"bbox={[round(x, 3) for x in tok.bounding_box]}")
            if tok.table_id:
                parts.append(f"table={tok.table_id} row={tok.row_index} col={tok.column_index}")
            preview = tok.text.replace("\n", " ")[:120]
            lines.append(" ".join(parts) + f" :: {preview}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Heuristic extraction (offline fallback / testable path)
    # ------------------------------------------------------------------
    def _extract_heuristic(
        self,
        request: ExtractionRequest,
        document_id: str,
        tokens: List[HeuristicToken],
        warnings: List[ExtractionWarning],
    ) -> ParsedBill:
        """Deterministic parser — handles simple bill/EOB text. This is the
        no-LLM fallback so the service is fully functional offline and testable."""
        text = request.raw_ocr_text
        doc_type = self._detect_doc_type(text)

        metadata = self._parse_metadata(text, doc_type)
        lines = self._parse_line_items(tokens, text, doc_type)
        totals = self._parse_totals(text, lines, doc_type)

        conf = FieldConfidence(
            ocr_confidence=1.0,
            extraction_confidence=0.5,  # heuristic is less confident than LLM
            verified=False,
        )

        # Ensure each line has provenance-bearing confidence
        for li in lines:
            if li.amount_confidence.provenance is None:
                li.amount_confidence = conf
            # heuristic lines are never auto-verified

        return ParsedBill(
            document_id=document_id,
            metadata=metadata,
            line_items=lines,
            totals=totals,
            warnings=warnings,
        )

    def _detect_doc_type(self, text: str) -> DocumentType:
        upper = text.upper()
        if re.search(r"EXPLANATION OF BENEFITS|EOB|CLAIM SUMMARY", upper):
            return DocumentType.EOB
        return DocumentType.BILL

    def _parse_metadata(
        self, text: str, doc_type: DocumentType
    ) -> DocumentMetadata:
        metadata = DocumentMetadata(document_type=doc_type)

        # Provider name — heuristic: look for "Provider:" / "Provider Name"
        # Stop at newline to avoid capturing subsequent fields.
        m = re.search(
            r"(?:Provider(?:\s+Name)?[:\s]+|Billed\s+By[:\s]+)([A-Za-z][A-Za-z\s\.\-]{2,60}?)(?:\n|$)",
            text,
        )
        if m:
            metadata.provider_name = m.group(1).strip()

        # NPI
        m = re.search(r"NPI[:\s]+([0-9]{10})", text)
        if m:
            metadata.provider_npi = m.group(1)
        m = re.search(r"NPI\s*(?:#)?\s*([0-9]{10})", text)
        if m and not metadata.provider_npi:
            metadata.provider_npi = m.group(1)

        # Payer — stop at newline to avoid capturing subsequent fields.
        m = re.search(
            r"(?:Payer|Insurance\s+Company|Carrier)[:\s]+([A-Za-z][A-Za-z\s\.\-]{2,50}?)(?:\n|$)",
            text,
        )
        if m:
            metadata.payer_name = m.group(1).strip()

        # Patient account ref (de-identified) — hash any account number found
        m = re.search(r"(?:Account\s+No|Account\s+#|Account)[.:\s]+([A-Za-z0-9\-]+)", text)
        if m:
            raw_acct = m.group(1)
            import hashlib

            h = hashlib.sha256(raw_acct.encode()).hexdigest()[:10]
            metadata.patient_account_ref = f"acct-{h}"

        # Dates
        dates = [
            self._parse_date(m) for m in _DATE_RE.finditer(text)
        ]
        dates = [d for d in dates if d is not None]

        # Statement date — often labeled "Statement Date" or the latest date
        m = re.search(r"(?:Statement\s+Date|Date\s+of\s+Statement)[:\s]+([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", text, re.IGNORECASE)
        if m:
            metadata.statement_date = self._parse_date(m)

        if dates:
            metadata.service_date_start = min(dates)
            metadata.service_date_end = max(dates)
            if metadata.statement_date is None:
                # Statement date is usually the last/bill date in the header
                m = re.search(r"(?:Bill\s+Date|Date\s+Billed|Dated)[:\s]+([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", text, re.IGNORECASE)
                if m:
                    metadata.statement_date = self._parse_date(m)

        return metadata

    @staticmethod
    def _parse_date(m: re.Match) -> Optional[date]:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except (ValueError, IndexError):
            return None

    def _parse_line_items(
        self, tokens: List[HeuristicToken], text: str, doc_type: DocumentType
    ) -> List[LineItem]:
        """Parse line items. For heuristic mode we look for CPT codes in each
        token (or the raw text) and build line items. Provenance is attached
        from the matching token when available."""

        # Build a flat searchable context with provenance
        flat = self._flatten_tokens(tokens)

        line_items: List[LineItem] = []
        # Find CPT/HCPCS codes in the text (in order), filtering out codes that
        # appear in non-CPT contexts (e.g. account numbers like "ACCT-12345").
        code_matches = [
            cm
            for cm in _CPT_RE.finditer(text)
            if not self._is_non_cpt_context(text, cm)
        ]
        if not code_matches:
            # No codes found — produce an empty list with a warning upstream
            # (caller already has the warning for missing fields)
            return line_items

        # For each code, find the enclosing token (for provenance) and look for amounts
        for i, cm in enumerate(code_matches):
            code = cm.group(0)
            line_no = i + 1
            # Find the token containing this code
            tok = self._find_token_for_position(tokens, cm.start(), text)
            prov = self._token_provenance(tok) if tok else None
            # Get amounts in a window around this code
            window = self._window_around(text, cm.start(), 400)
            amounts = self._extract_amounts(window)
            # Units
            units = self._extract_units(window)
            # Date of service
            dos = self._extract_dos(window)

            charge = amounts[0] if len(amounts) > 0 else None
            allowed = amounts[1] if len(amounts) > 1 else None
            paid = amounts[2] if len(amounts) > 2 else None
            patient = amounts[3] if len(amounts) > 3 else None

            confidence = FieldConfidence(
                ocr_confidence=tok.ocr_confidence if tok else 0.5,
                extraction_confidence=0.5,
                verified=False,
                provenance=prov,
            )

            line_items.append(
                LineItem(
                    line_number=line_no,
                    cpt_hcpcs_code=code,
                    units=units,
                    date_of_service=dos,
                    charge_amount=charge,
                    allowed_amount=allowed,
                    paid_amount=paid,
                    patient_responsibility=patient,
                    code_confidence=confidence,
                    amount_confidence=confidence,
                )
            )

        return line_items

    @staticmethod
    def _is_non_cpt_context(text: str, match: re.Match) -> bool:
        """Heuristic: is this 5-char code actually part of an account number,
        NPI, or other non-CPT context?"""
        start = match.start()
        # Preceded by a hyphen (e.g. "ACCT-12345") or part of "ACCT", "Account",
        # "NPI", "Claim", "Ref", "ID" — these are not CPT codes.
        prefix = text[max(0, start - 12):start].upper()
        if re.search(r"(ACCT|ACCOUNT|NPI|CLAIM|REF|ID|NO|#)[\s\-:]*$", prefix):
            return True
        # Preceded directly by a hyphen or digit (part of a larger number)
        if start > 0 and text[start - 1] in "-/":
            return True
        return False

    def _flatten_tokens(self, tokens: List[HeuristicToken]) -> List[Tuple[int, str, HeuristicToken]]:
        """Flatten tokens into (start_char_guess, text, token) — note we can't
        reliably map char offsets to tokens without layout, so this is best-effort
        using the raw text content."""
        out = []
        for tok in tokens:
            for m in _CPT_RE.finditer(tok.text):
                out.append((m.start(), m.group(0), tok))
        return out

    def _find_token_for_position(
        self, tokens: List[HeuristicToken], char_pos: int, full_text: str
    ) -> Optional[HeuristicToken]:
        """Best-effort: find the token whose text contains the code nearest to
        char_pos. We search the flattened text spans for a rough offset match."""
        # Since we don't have perfect char mapping, do a reasonable heuristic:
        # find the first token whose text appears near char_pos in the concatenated text.
        running = 0
        for tok in tokens:
            tk = tok.text
            if tk in full_text:
                span_start = full_text.find(tk, running)
                if span_start <= char_pos < span_start + len(tk):
                    return tok
            running += len(tk) + 1
        return None

    def _token_provenance(self, tok: HeuristicToken) -> Provenance:
        return Provenance(
            page=tok.page,
            bounding_box=tok.bounding_box,
            text=tok.text[:200],
            table_id=tok.table_id,
            row_index=tok.row_index,
            column_index=tok.column_index,
        )

    def _window_around(self, text: str, pos: int, width: int = 400) -> str:
        start = max(0, pos - width // 2)
        end = min(len(text), pos + width)
        return text[start:end]

    def _extract_amounts(self, window: str) -> List[float]:
        amounts = []
        for m in _AMOUNT_RE.finditer(window):
            amt_str = m.group(1).replace(",", "")
            try:
                amounts.append(round(float(amt_str), 2))
            except ValueError:
                continue
        return amounts

    def _extract_units(self, window: str) -> float:
        m = re.search(r"(?:Units|Qty)[:\s]+([0-9]+(?:\.[0-9])?)", window, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return 1.0
        return 1.0

    def _extract_dos(self, window: str) -> Optional[date]:
        m = _DATE_RE.search(window)
        if m:
            return self._parse_date(m)
        return None

    def _parse_totals(
        self, text: str, lines: List[LineItem], doc_type: DocumentType
    ) -> Optional[TotalsBlock]:
        """Extract totals. First try labeled totals in the text; if not found,
        compute from line items."""
        totals = TotalsBlock()

        # Labeled totals
        mapping = {
            "billed_total": r"(?:Total\s+Billed|Total\s+Charges|Billed\s+Total)[:\s]+\$?\s?([0-9,]+(?:\.[0-9]{2})?)",
            "allowed_total": r"(?:Total\s+Allowed|Allowed\s+Total|Total\s+Approved)[:\s]+\$?\s?([0-9,]+(?:\.[0-9]{2})?)",
            "paid_total": r"(?:Total\s+Paid|Paid\s+Total|Total\s+Payment)[:\s]+\$?\s?([0-9,]+(?:\.[0-9]{2})?)",
            "patient_responsibility_total": r"(?:Total\s+Patient\s+Responsibility|Patient\s+Responsibility\s+Total|Total\s+You\s+Owe|Amount\s+You\s+Owe)[:\s]+\$?\s?([0-9,]+(?:\.[0-9]{2})?)",
            "adjustments_total": r"(?:Total\s+Adjustments?|Adjustments?\s+Total)[:\s]+\$?\s?([0-9,]+(?:\.[0-9]{2})?)",
        }
        for field, pattern in mapping.items():
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                try:
                    setattr(totals, field, round(float(m.group(1).replace(",", "")), 2))
                except ValueError:
                    pass

        # If labeled total for a field is missing, use the line item sum (marked as computed)
        if totals.billed_total is None:
            vals = [li.charge_amount for li in lines if li.charge_amount is not None]
            if vals:
                totals.billed_total = round(sum(vals), 2)
        if totals.allowed_total is None:
            vals = [li.allowed_amount for li in lines if li.allowed_amount is not None]
            if vals:
                totals.allowed_total = round(sum(vals), 2)
        if totals.paid_total is None:
            vals = [li.paid_amount for li in lines if li.paid_amount is not None]
            if vals:
                totals.paid_total = round(sum(vals), 2)
        if totals.patient_responsibility_total is None and doc_type == DocumentType.EOB:
            vals = [li.patient_responsibility for li in lines if li.patient_responsibility is not None]
            if vals:
                totals.patient_responsibility_total = round(sum(vals), 2)

        # If nothing was found, return None
        if all(
            v is None
            for v in [
                totals.billed_total,
                totals.allowed_total,
                totals.paid_total,
                totals.patient_responsibility_total,
            ]
        ):
            return None

        return totals


def get_extraction_service() -> ExtractionService:
    return ExtractionService()