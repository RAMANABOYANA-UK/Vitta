"""
Client for the Rust bill_rules service.

This module is the only place that knows how to talk to the deterministic
rules engine. The rest of the backend just calls `apply_rules()`.

Contract:
  The Rust service treats the full ParsedBill as opaque JSON. It only reads
  and writes `line_items` and `totals` — it never drops unknown fields
  (patient, provider, letter, audit, etc.) even as the Python schema evolves.

Behavior:
  - If RULES_ENGINE_ENABLED is False → returns the bill unchanged
  - If the service is unreachable or times out → logs a warning and returns
    the original bill (graceful degradation)
  - On success → returns the bill with real deterministic flags merged in
"""

import logging

import httpx

from app.config import settings
from app.schemas import ParsedBill

logger = logging.getLogger(__name__)


async def apply_rules(bill: ParsedBill) -> ParsedBill:
    """
    Send a ParsedBill to the Rust rules engine and return the enriched version.

    The full bill is sent as opaque JSON. The Rust service only touches
    line_items and totals, preserving all other fields (patient, provider,
    letter, audit, etc.) even as the Python schema evolves.
    """
    if not settings.RULES_ENGINE_ENABLED:
        logger.info("Rules engine disabled — skipping")
        return bill

    url = f"{settings.RULES_ENGINE_URL.rstrip('/')}/apply-rules"

    try:
        async with httpx.AsyncClient(
            timeout=settings.RULES_ENGINE_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(url, json=bill.model_dump(mode="json"))
            response.raise_for_status()
            enriched = ParsedBill.model_validate(response.json())

    except httpx.TimeoutException:
        logger.warning(
            "Rules engine timed out after %.1fs — continuing without rules | document_id=%s",
            settings.RULES_ENGINE_TIMEOUT_SECONDS,
            bill.document_id,
        )
        return bill

    except httpx.ConnectError:
        logger.warning(
            "Rules engine unreachable at %s — continuing without rules",
            url,
        )
        return bill

    except httpx.HTTPStatusError as e:
        logger.error(
            "Rules engine returned HTTP %s — continuing without rules | body=%s",
            e.response.status_code,
            e.response.text[:500],
        )
        return bill

    except Exception:
        logger.exception(
            "Unexpected error calling rules engine — continuing without rules | document_id=%s",
            bill.document_id,
        )
        return bill

    total_flags = sum(len(item.flags) for item in enriched.line_items)
    logger.info(
        "Rules engine applied successfully | document_id=%s | flags=%d",
        enriched.document_id,
        total_flags,
    )
    return enriched