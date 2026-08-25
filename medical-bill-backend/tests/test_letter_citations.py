"""Unit tests for the letter citation fabrication policy.

The verifier historically never checked statutory/regulatory citations — the
highest-liability unguarded gap in the system. These tests lock in the new
config-guarded guard (off by default, allow-list enforced when enabled).
"""

from __future__ import annotations

from app.config import settings
from app.schemas import ParsedBill
from app.services.letter_verifier import _CITATION_RE, verify_letter


def _make_bill() -> ParsedBill:
    from app.schemas import LineItem, Totals

    return ParsedBill(
        document_id="ct-1",
        status="letter_ready",
        source_type="bill",
        uploaded_at="2026-08-01T00:00:00",
        patient={},
        provider={"name": "Memorial", "npi": "1234567893"},
        payer={"name": "Blue", "claim_number": "GX-1"},
        service_date="2026-07-22",
        line_items=[
            LineItem(
                id="li-1",
                description="ER visit",
                cpt_hcpcs="99284",
                charge_amount=1240.0,
                allowed_amount=800.0,
                paid_amount=650.0,
                patient_responsibility=150.0,
            )
        ],
        totals=Totals(billed=1240.0, allowed=800.0, insurance_paid=650.0, patient_responsibility=150.0),
    )


def test_citation_regex_matches_statutory_citations():
    assert _CITATION_RE.search("per 42 U.S.C. 1395 telemedicine rules")
    assert _CITATION_RE.search("under 45 CFR 164.512")
    assert _CITATION_RE.search("29 U.S.C. § 1132")


def test_citation_regex_ignores_plain_numbers():
    assert not _CITATION_RE.search("The claim GX-1 for CPT 99284 on 07/22/2026")


def test_policy_off_ignores_fabricated_citation():
    """Default policy 'off' preserves current behavior — no citation check."""
    orig = settings.CITATION_FABRICATION_POLICY
    settings.CITATION_FABRICATION_POLICY = "off"
    try:
        bill = _make_bill()
        _, _, problems = verify_letter(
            bill,
            "Re: Claim GX-1. We dispute the denial and note 42 U.S.C. 1395 does not apply.",
        )
        # No fabricated-citation problem raised when policy is off.
        assert not any("Citation" in p for p in problems)
    finally:
        settings.CITATION_FABRICATION_POLICY = orig


def test_policy_warn_flags_unapproved_citation():
    orig_policy = settings.CITATION_FABRICATION_POLICY
    orig_allowed = settings.ALLOWED_CITATIONS
    settings.CITATION_FABRICATION_POLICY = "warn"
    settings.ALLOWED_CITATIONS = ""
    try:
        bill = _make_bill()
        ok, _, problems = verify_letter(
            bill,
            "Re: Claim GX-1. We dispute it under 45 CFR 164 fabricated-section.",
        )
        assert not ok
        assert any("45 CFR" in p or "Citation" in p for p in problems)
    finally:
        settings.CITATION_FABRICATION_POLICY = orig_policy
        settings.ALLOWED_CITATIONS = orig_allowed


def test_policy_warn_allows_approved_citation():
    orig_policy = settings.CITATION_FABRICATION_POLICY
    orig_allowed = settings.ALLOWED_CITATIONS
    settings.CITATION_FABRICATION_POLICY = "warn"
    settings.ALLOWED_CITATIONS = "42 U.S.C. 1395"
    try:
        bill = _make_bill()
        ok, _, problems = verify_letter(
            bill,
            "Re: Claim GX-1. Per 42 U.S.C. 1395 (an approved citation) we appeal.",
        )
        assert not any("Citation" in p for p in problems)
    finally:
        settings.CITATION_FABRICATION_POLICY = orig_policy
        settings.ALLOWED_CITATIONS = orig_allowed