"""Regression tests for P0 #3 — the pipeline's letter verification gate.

Bug: pipeline.py reported ``verification_passed = len(verified_fields) > 0``.
A letter can carry verified fields AND unresolved problems at the same time
(e.g. a correct claim number plus a hallucinated dollar amount), so that proxy
reported a partially-verified letter as fully passed. The authoritative signal
is the verifier's "zero problems" result, now carried on Letter.verification_passed.

These tests run the REAL run_pipeline with the three stage functions monkeypatched,
and assert the audit reflects the authoritative outcome. The first test fails
against the old code.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas import DocumentStatus, Letter, ParsedBill, Totals
from app.services import pipeline as pipeline_mod


def _make_bill() -> ParsedBill:
    return ParsedBill(
        document_id="DOC-1",
        status=DocumentStatus.processing,
        uploaded_at=datetime.now(timezone.utc),
        source_type="pdf",
        totals=Totals(billed=100.0),
        line_items=[],
    )


def _patch_stages(monkeypatch, letter: Letter) -> None:
    bill = _make_bill()

    async def fake_extract_and_score(**kwargs):
        return bill

    async def fake_apply_rules(b):
        return b

    async def fake_generate_appeal_letter(b):
        return letter

    monkeypatch.setattr(pipeline_mod, "extract_and_score", fake_extract_and_score)
    monkeypatch.setattr(pipeline_mod, "apply_rules", fake_apply_rules)
    monkeypatch.setattr(pipeline_mod, "generate_appeal_letter", fake_generate_appeal_letter)
    monkeypatch.setattr(pipeline_mod.settings, "PIPELINE_DELAY_SECONDS", 0, raising=False)


@pytest.mark.asyncio
async def test_verified_fields_with_problems_do_not_pass(monkeypatch):
    """The core regression: verified fields present, but a problem exists →
    verification_passed must be False (old code returned True)."""
    letter = Letter(
        status="draft",
        content_markdown="Re: Appeal ...",
        verified_fields=["claim_number", "service_date"],
        verification_passed=False,
        problems=["Amount $999.99 doesn't match any known figure on the bill"],
    )
    _patch_stages(monkeypatch, letter)

    result = await pipeline_mod.run_pipeline("DOC-1", "bill.pdf")
    letter_audit = result.audit["letter"]

    assert letter_audit["verified_fields_count"] == 2
    assert letter_audit["verification_passed"] is False
    assert letter_audit["problems"] == [
        "Amount $999.99 doesn't match any known figure on the bill"
    ]


@pytest.mark.asyncio
async def test_clean_letter_passes(monkeypatch):
    """A letter with zero problems passes and reports no problems."""
    letter = Letter(
        status="draft",
        content_markdown="Re: Appeal ...",
        verified_fields=["claim_number"],
        verification_passed=True,
        problems=[],
    )
    _patch_stages(monkeypatch, letter)

    result = await pipeline_mod.run_pipeline("DOC-1", "bill.pdf")
    letter_audit = result.audit["letter"]

    assert letter_audit["verification_passed"] is True
    assert letter_audit["problems"] == []


@pytest.mark.asyncio
async def test_no_verified_fields_but_clean_still_passes(monkeypatch):
    """A letter that legitimately has nothing to verify (no problems) passes —
    the inverse failure the old count-based check would also have gotten wrong."""
    letter = Letter(
        status="draft",
        content_markdown="Re: Appeal of Medical Bill ...",
        verified_fields=[],
        verification_passed=True,
        problems=[],
    )
    _patch_stages(monkeypatch, letter)

    result = await pipeline_mod.run_pipeline("DOC-1", "bill.pdf")
    letter_audit = result.audit["letter"]

    assert letter_audit["verified_fields_count"] == 0
    assert letter_audit["verification_passed"] is True
