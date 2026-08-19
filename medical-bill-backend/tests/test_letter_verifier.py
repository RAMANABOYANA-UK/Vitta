from datetime import date, datetime, timezone
from app.schemas import ParsedBill, LineItem, Totals, DocumentStatus
from app.services.letter_verifier import verify_letter


def make_bill(**overrides) -> ParsedBill:
    defaults = dict(
        document_id="doc-1",
        status=DocumentStatus.letter_ready,
        uploaded_at=datetime.now(timezone.utc),
        source_type="test",
        patient={"name": "Jane Doe", "member_id": "M123"},
        provider={"name": "Memorial Hospital", "npi": "1234567893"},
        payer={"name": "Acme Insurance", "claim_number": "GX-2025-883241"},
        service_date=date(2026, 7, 22),
        line_items=[
            LineItem(id="LI-1", description="ER visit", cpt_hcpcs="99284",
                      charge_amount=1240.00, allowed_amount=800.00,
                      paid_amount=650.00, patient_responsibility=150.00),
            LineItem(id="LI-2", description="Facility fee", cpt_hcpcs="G0463",
                      charge_amount=540.00, allowed_amount=400.00,
                      paid_amount=320.00, patient_responsibility=80.00),
        ],
        totals=Totals(billed=1780.00, allowed=1200.00, insurance_paid=970.00,
                       patient_responsibility=230.00),
        denial_codes=[{"code": "CO-97", "reason": "bundled service"}],
    )
    defaults.update(overrides)
    return ParsedBill(**defaults)


def test_known_hcpcs_code_verified():
    bill = make_bill()
    ok, verified, problems = verify_letter(
        bill, "Re: Appeal of Claim GX-2025-883241\n\nWe dispute HCPCS G0463 billed on 07/22/2026."
    )
    assert ok and "code_G0463" in verified and not problems


def test_hallucinated_hcpcs_code_caught():
    bill = make_bill()
    ok, verified, problems = verify_letter(bill, "Re: Appeal\n\nThe charge for HCPCS G9999 is disputed.")
    assert not ok and any("G9999" in p for p in problems)


def test_zip_code_not_false_flagged():
    bill = make_bill()
    ok, verified, problems = verify_letter(
        bill, "Re: Appeal\n\nPatient address: 123 Main St, Springfield, IL 90210.\nWe dispute CPT 99284."
    )
    assert not any("90210" in p for p in problems)
    assert "code_99284" in verified


def test_hallucinated_denial_code_caught():
    bill = make_bill()
    ok, verified, problems = verify_letter(bill, "Re: Appeal\n\nThis claim was denied under CO-45, which we contest.")
    assert not ok and any("CO-45" in p for p in problems)


def test_real_denial_code_verified():
    bill = make_bill()
    ok, verified, problems = verify_letter(
        bill,
        "Re: Appeal of Claim GX-2025-883241\n\n"
        "For services on 07/22/2026, this claim was denied under CO-97, which we contest.",
    )
    assert ok and "denial_CO-97" in verified


def test_hallucinated_npi_caught():
    bill = make_bill()
    ok, verified, problems = verify_letter(bill, "Re: Appeal\n\nProvider NPI 9999999999 submitted this claim.")
    assert not ok and any("9999999999" in p for p in problems)


def test_real_npi_verified():
    bill = make_bill()
    ok, verified, problems = verify_letter(
        bill,
        "Re: Appeal of Claim GX-2025-883241\n\n"
        "For services on 07/22/2026, provider NPI 1234567893 submitted this claim.",
    )
    assert ok and "provider_npi" in verified


def test_no_regression_on_existing_checks():
    bill = make_bill()
    letter = ("Re: Appeal of Claim GX-2025-883241\n\n"
              "For services on July 22, 2026, we dispute the $1,240.00 charge "
              "(CPT 99284), of which $150.00 became patient responsibility.")
    ok, verified, problems = verify_letter(bill, letter)
    assert ok
    assert "claim_number" in verified
    assert "service_date" in verified
    assert "amount_1240.0" in verified
    assert "amount_150.0" in verified
    assert "code_99284" in verified


def test_denial_code_under_carc_field_verified():
    """Denial codes may arrive under `carc` (X12/837 format) instead of `code`."""
    bill = make_bill(denial_codes=[{"carc": "CO-97", "reason": "bundled service"}])
    ok, verified, problems = verify_letter(
        bill,
        "Re: Appeal of Claim GX-2025-883241\n\n"
        "For services on 07/22/2026, this claim was denied under CO-97, which we contest.",
    )
    assert ok and "denial_CO-97" in verified


def test_denial_code_under_rarc_field_verified():
    """Denial codes may arrive under `rarc` (X12/835 remark code) instead of `code`."""
    bill = make_bill(denial_codes=[{"rarc": "N362", "reason": "remark code"}])
    ok, verified, problems = verify_letter(
        bill,
        "Re: Appeal of Claim GX-2025-883241\n\n"
        "For services on 07/22/2026, this claim was denied under N362, which we contest.",
    )
    assert ok and "denial_N362" in verified


def test_denial_code_mixed_fields_all_checked():
    """Multiple denial codes under different field names are all verified."""
    bill = make_bill(
        denial_codes=[
            {"code": "CO-97", "reason": "bundled"},
            {"carc": "PR-4", "reason": "modifier"},
            {"rarc": "N362", "reason": "remark"},
        ]
    )
    ok, verified, problems = verify_letter(
        bill,
        "Re: Appeal of Claim GX-2025-883241\n\n"
        "For services on 07/22/2026, this claim was denied under CO-97, PR-4, and N362.",
    )
    assert ok
    assert "denial_CO-97" in verified
    assert "denial_PR-4" in verified
    assert "denial_N362" in verified
    assert not problems
