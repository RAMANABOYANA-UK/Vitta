"""Regression tests for P0 #1 — the Totals `_total` alias set.

app/db.py's save_parsed_bill reads all four totals via their `_total` names
(billed_total, allowed_total, paid_total, patient_responsibility_total). Two of
those aliases (allowed_total, paid_total) were missing from the Totals model,
so building a ParsedBillRecord raised AttributeError and returned HTTP 500 from
/validate, /score and /pipeline whenever DATABASE_URL was configured. The bug
was invisible because there was no test touching app/db.py.

These tests pin the read/write contract and exercise the real ORM class, so the
alias set cannot silently regress again.
"""

from __future__ import annotations

from app.db import ParsedBillRecord
from app.models import Totals


def test_totals_exposes_all_four_total_aliases() -> None:
    totals = Totals(
        billed=1000.0,
        allowed=800.0,
        insurance_paid=600.0,
        patient_responsibility=200.0,
    )
    # Exactly the reads app/db.py.save_parsed_bill performs.
    assert totals.billed_total == 1000.0
    assert totals.allowed_total == 800.0
    assert totals.paid_total == 600.0
    assert totals.patient_responsibility_total == 200.0


def test_total_aliases_are_writable() -> None:
    totals = Totals(billed=0.0)
    totals.billed_total = 500.0
    totals.allowed_total = 400.0
    totals.paid_total = 300.0
    totals.patient_responsibility_total = 100.0
    assert totals.billed == 500.0
    assert totals.allowed == 400.0
    assert totals.insurance_paid == 300.0
    assert totals.patient_responsibility == 100.0


def test_parsedbillrecord_builds_from_totals_without_attributeerror() -> None:
    """The exact record-construction block from db.save_parsed_bill (L131-136)
    that previously raised AttributeError. Uses the real ORM class; no DB
    connection required to instantiate it."""
    totals = Totals(
        billed=1000.0,
        allowed=800.0,
        insurance_paid=600.0,
        patient_responsibility=200.0,
    )
    record = ParsedBillRecord(
        document_id="DOC-1",
        document_type="bill",
        billed_total=totals.billed_total if totals else None,
        allowed_total=totals.allowed_total if totals else None,
        paid_total=totals.paid_total if totals else None,
        patient_responsibility_total=(
            totals.patient_responsibility_total if totals else None
        ),
        payload={},
    )
    assert record.allowed_total == 800.0
    assert record.paid_total == 600.0


def test_none_totals_guard_still_works() -> None:
    """The `if totals else None` guard must remain valid when totals is None."""
    totals = None
    assert (totals.allowed_total if totals else None) is None
    assert (totals.paid_total if totals else None) is None
