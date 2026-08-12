"""
Client for the Rust bill_rules service.

This module is the only place that knows how to talk to the deterministic
rules engine. The rest of the backend just calls `apply_rules()`.

Contract:
  The Rust service accepts a *subset* of the full ParsedBill — only the
  fields the rules engine operates on (document_id, status, service_date,
  line_items, totals). The Python client extracts that subset, sends it,
  and merges the enriched flags back into the full bill. This keeps the
  wire contract small, versioned, and stable while preserving all the
  extra fields the Python backend owns (patient, provider, payer, etc.).

Behavior:
  - If RULES_ENGINE_ENABLED is False → returns the bill unchanged
  - If the service is unreachable or times out → logs a warning and returns
    the original bill (graceful degradation)
  - On success → returns the bill with real deterministic flags merged in
"""

import logging
from typing import Optional

import httpx
from pydantic import BaseModel

from app.config import settings
from app.schemas import Flag, LineItem, ParsedBill, Totals

logger = logging.getLogger(__name__)


class RulesEngineError(Exception):
    """Raised when the rules engine call fails permanently."""


# ---------------------------------------------------------------------------
# Wire contract — mirrors the Rust `ParsedBill` schema in bill_rules/src/types.rs
# ---------------------------------------------------------------------------

class _RulesLineItem(BaseModel):
    """Line item subset sent to / received from the Rust engine."""

    id: str
    page: int = 1
    description: str
    cpt_hcpcs: Optional[str] = None
    icd10: list[str] = []
    units: float = 1.0
    charge_amount: float
    allowed_amount: Optional[float] = None
    paid_amount: Optional[float] = None
    patient_responsibility: Optional[float] = None
    modifiers: list[str] = []
    flags: list[Flag] = []


class _RulesTotals(BaseModel):
    """Totals subset sent to / received from the Rust engine."""

    billed: float
    allowed: Optional[float] = None
    insurance_paid: Optional[float] = None
    patient_responsibility: Optional[float] = None
    potential_savings: Optional[float] = None


class _RulesBill(BaseModel):
    """The exact JSON shape the Rust service expects (bill_rules::ParsedBill)."""

    document_id: str
    status: str
    service_date: Optional[str] = None
    line_items: list[_RulesLineItem] = []
    totals: _RulesTotals


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def apply_rules(bill: ParsedBill) -> ParsedBill:
    """
    Send a ParsedBill to the Rust rules engine and return the enriched version.

    The full bill is preserved; only the flags on line items are updated
    based on the deterministic rules engine's output.
    """
    if not settings.RULES_ENGINE_ENABLED:
        logger.info("Rules engine disabled – skipping")
        return bill

    url = f"{settings.RULES_ENGINE_URL.rstrip('/')}/apply-rules"

    # 1. Extract the rules-relevant subset
    payload = _extract_rules_subset(bill)

    try:
        async with httpx.AsyncClient(
            timeout=settings.RULES_ENGINE_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(url, json=payload.model_dump(mode="json"))
            response.raise_for_status()

            enriched_payload = _RulesBill.model_validate(response.json())

    except httpx.TimeoutException:
        logger.warning(
            "Rules engine timed out after %.1fs – continuing without rules | document_id=%s",
            settings.RULES_ENGINE_TIMEOUT_SECONDS,
            bill.document_id,
        )
        return bill

    except httpx.HTTPStatusError as e:
        logger.error(
            "Rules engine returned HTTP %s – continuing without rules | document_id=%s",
            e.response.status_code,
            bill.document_id,
        )
        return bill

    except Exception as e:
        logger.exception(
            "Unexpected error calling rules engine – continuing without rules | document_id=%s | error=%s",
            bill.document_id,
            str(e),
        )
        return bill

    # 2. Merge the enriched flags back into the full bill
    enriched = _merge_flags(bill, enriched_payload)

    total_flags = sum(len(item.flags) for item in enriched.line_items)
    logger.info(
        "Rules engine applied successfully | document_id=%s | flags=%d",
        enriched.document_id,
        total_flags,
    )
    return enriched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_rules_subset(bill: ParsedBill) -> _RulesBill:
    """Extract the rules-relevant subset of the full bill for the wire contract."""
    return _RulesBill(
        document_id=bill.document_id,
        status=bill.status.value,
        service_date=bill.service_date.isoformat() if bill.service_date else None,
        line_items=[
            _RulesLineItem(
                id=item.id,
                page=item.page,
                description=item.description,
                cpt_hcpcs=item.cpt_hcpcs,
                icd10=item.icd10,
                units=item.units,
                charge_amount=item.charge_amount,
                allowed_amount=item.allowed_amount,
                paid_amount=item.paid_amount,
                patient_responsibility=item.patient_responsibility,
                modifiers=item.modifiers,
                flags=item.flags,
            )
            for item in bill.line_items
        ],
        totals=_RulesTotals(
            billed=bill.totals.billed,
            allowed=bill.totals.allowed,
            insurance_paid=bill.totals.insurance_paid,
            patient_responsibility=bill.totals.patient_responsibility,
            potential_savings=bill.totals.potential_savings,
        ),
    )


def _merge_flags(original: ParsedBill, enriched: _RulesBill) -> ParsedBill:
    """
    Merge the enriched flags from the Rust engine back into the full bill.

    Flags are matched by line item id. Any flags the engine produced are
    attached to the corresponding line item; line items not present in the
    engine response keep their original flags.
    """
    enriched_by_id = {item.id: item for item in enriched.line_items}

    merged_line_items: list[LineItem] = []
    for item in original.line_items:
        enriched_item = enriched_by_id.get(item.id)
        if enriched_item is not None:
            # Replace flags with the engine's deterministic output
            merged_line_items.append(
                item.model_copy(update={"flags": enriched_item.flags})
            )
        else:
            merged_line_items.append(item)

    return original.model_copy(update={"line_items": merged_line_items})