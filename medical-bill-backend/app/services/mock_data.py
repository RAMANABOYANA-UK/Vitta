"""
Realistic mock data generator for the medical bill pipeline.

Generates a complete ParsedBill structure with believable patient/provider/payer
information, line items with CPT/HCPCS codes, ICD-10 diagnoses, charge/paid
amounts, denial codes, appeal prediction, and a sample appeal letter.

This allows the frontend and other team members to build against real API
shapes before the actual extraction and Rust rules engine are integrated.
"""
import random
import uuid
from datetime import date, datetime, timedelta, timezone

from app.schemas import (
    AppealPrediction,
    DocumentStatus,
    Flag,
    Letter,
    LineItem,
    ParsedBill,
    Totals,
)

# ---------------------------------------------------------------------------
# Pool of realistic data
# ---------------------------------------------------------------------------

PATIENTS = [
    {
        "name": "Sarah Mitchell",
        "dob": "1985-06-12",
        "gender": "F",
        "member_id": "M-100234-01",
        "address": "482 Oakwood Drive, Portland, OR 97205",
    },
    {
        "name": "James Rodriguez",
        "dob": "1972-11-03",
        "gender": "M",
        "member_id": "M-207651-02",
        "address": "1234 Maple Avenue, Austin, TX 78701",
    },
    {
        "name": "Emily Chen",
        "dob": "1991-02-28",
        "gender": "F",
        "member_id": "M-348920-03",
        "address": "778 Rosewood Lane, Seattle, WA 98101",
    },
]

PROVIDERS = [
    {
        "name": "Northside Medical Center",
        "npi": "1234567890",
        "tax_id": "93-1234567",
        "address": "900 Health Sciences Blvd, Portland, OR 97239",
        "phone": "(503) 555-0134",
    },
    {
        "name": "Austin Regional Hospital",
        "npi": "2345678901",
        "tax_id": "74-2345678",
        "address": "1500 Red River St, Austin, TX 78712",
        "phone": "(512) 555-0178",
    },
    {
        "name": "Pacific General Medical Group",
        "npi": "3456789012",
        "tax_id": "91-3456789",
        "address": "1100 9th Avenue, Seattle, WA 98101",
        "phone": "(206) 555-0145",
    },
]

PAYERS = [
    {
        "name": "BlueCross BlueShield of Oregon",
        "payer_id": "80068",
        "phone": "(800) 555-0100",
        "claim_number": "GX-2025-883241",
    },
    {
        "name": "UnitedHealthcare",
        "payer_id": "87726",
        "phone": "(800) 555-0200",
        "claim_number": "UHC-44789012",
    },
    {
        "name": "Aetna",
        "payer_id": "50027",
        "phone": "(800) 555-0300",
        "claim_number": "AET-90213456",
    },
]

# (description, cpt_hcpcs, icd10, base_charge, modifiers)
LINE_ITEM_TEMPLATES = [
    ("Emergency department visit, level 4", "99284", ["I10", "R10.9"], 1250.00, ["25"]),
    ("Comprehensive metabolic panel", "80053", ["E11.9", "I10"], 145.00, []),
    ("Chest X-ray, 2 views", "71046", ["J44.9", "R05"], 250.00, []),
    ("CT scan of abdomen and pelvis with contrast", "74177", ["K57.30", "R10.9"], 2850.00, []),
    ("Physical therapy evaluation", "97161", ["M54.5", "M47.816"], 180.00, []),
    ("Electrocardiogram, routine", "93000", ["I48.91", "R00.1"], 95.00, []),
    ("Complete blood count (CBC) with differential", "85025", ["D64.9", "R53.83"], 85.00, []),
    ("Magnetic resonance imaging of brain without contrast", "70551", ["G43.909", "R51"], 3200.00, []),
    ("Colonoscopy, diagnostic", "45378", ["K63.5", "Z12.11"], 2100.00, []),
    ("Ultrasound of abdomen complete", "76700", ["K76.9", "R10.9"], 420.00, []),
]

DENIAL_CODES = [
    {
        "code": "CO-50",
        "reason": "This service was not medically necessary.",
        "severity": "critical",
        "amount": 1250.00,
    },
    {
        "code": "CO-97",
        "reason": "The service or procedure was not medically necessary.",
        "severity": "critical",
        "amount": 2850.00,
    },
    {
        "code": "PR-4",
        "reason": "Procedure code is inconsistent with the modifier used or a required modifier is missing.",
        "severity": "warning",
        "amount": 180.00,
    },
    {
        "code": "CO-151",
        "reason": "Payment adjusted because the payer deems the information submitted does not support this level of service.",
        "severity": "warning",
        "amount": 3200.00,
    },
    {
        "code": "OA-23",
        "reason": "Payment adjusted because this procedure code was not covered by this plan.",
        "severity": "info",
        "amount": 95.00,
    },
]


def _random_choice(pool: list) -> dict:
    return random.choice(pool)


def _build_flag_objects(line_item: dict, index: int) -> list[Flag]:
    """Generate plausible flags for a line item."""
    flags: list[Flag] = []
    rng = random.random()

    if rng < 0.35:
        flags.append(
            Flag(
                type="price_inflated",
                severity="warning",
                message=(
                    f"Charge of ${line_item['charge_amount']:,.2f} is "
                    f"{random.randint(15, 60)}% above the 75th percentile "
                    f"for CPT {line_item['cpt_hcpcs']} in this region."
                ),
                rule_id="RULE-PRICE-001",
                shap_contribution=round(random.uniform(0.15, 0.45), 4),
            )
        )

    if rng < 0.25:
        flags.append(
            Flag(
                type="billing_code_mismatch",
                severity="critical",
                message=(
                    f"CPT {line_item['cpt_hcpcs']} appears inconsistent with "
                    f"documented ICD-10 codes {', '.join(line_item['icd10'])}."
                ),
                rule_id="RULE-CODE-017",
                shap_contribution=round(random.uniform(0.3, 0.6), 4),
            )
        )

    if random.random() < 0.2:
        flags.append(
            Flag(
                type="bundled_service",
                severity="info",
                message=(
                    f"Service may be eligible for bundling under "
                    f"National Correct Coding Initiative (NCCI) edits."
                ),
                rule_id="RULE-NCCI-023",
                shap_contribution=round(random.uniform(0.05, 0.2), 4),
            )
        )

    return flags


def _build_line_items(patient: dict, provider: dict) -> list[LineItem]:
    """Generate 3-6 realistic line items."""
    num_items = random.randint(3, 6)
    templates = random.sample(LINE_ITEM_TEMPLATES, num_items)
    line_items: list[LineItem] = []

    for idx, (desc, cpt, icd10, base_charge, modifiers) in enumerate(templates, start=1):
        units = round(random.uniform(1, 3), 0)
        charge = round(base_charge * units * random.uniform(1.0, 1.4), 2)
        # Allow/paid are sometimes absent when the claim was fully denied
        if random.random() < 0.75:
            allowed = round(charge * random.uniform(0.45, 0.7), 2)
            paid = round(allowed * random.uniform(0.75, 0.9), 2)
            patient_resp = round(allowed - paid, 2)
        else:
            allowed = None
            paid = None
            patient_resp = charge

        line_item_dict = {
            "description": desc,
            "cpt_hcpcs": cpt,
            "icd10": icd10,
            "units": units,
            "charge_amount": charge,
            "allowed_amount": allowed,
            "paid_amount": paid,
            "patient_responsibility": patient_resp,
            "modifiers": modifiers,
        }

        line_items.append(
            LineItem(
                id=f"LI-{idx}-{uuid.uuid4().hex[:8].upper()}",
                page=random.randint(1, 2),
                description=desc,
                cpt_hcpcs=cpt,
                icd10=list(icd10),
                units=units,
                charge_amount=charge,
                allowed_amount=allowed,
                paid_amount=paid,
                patient_responsibility=patient_resp,
                modifiers=list(modifiers),
                flags=_build_flag_objects(line_item_dict, idx),
            )
        )

    return line_items


def _build_totals(line_items: list[LineItem]) -> Totals:
    """Aggregate totals from line items."""
    billed = round(sum(item.charge_amount for item in line_items), 2)
    allowed_values = [i.allowed_amount for i in line_items if i.allowed_amount is not None]
    paid_values = [i.paid_amount for i in line_items if i.paid_amount is not None]
    resp_values = [i.patient_responsibility for i in line_items if i.patient_responsibility is not None]

    allowed = round(sum(allowed_values), 2) if allowed_values else None
    insurance_paid = round(sum(paid_values), 2) if paid_values else None
    patient_resp = round(sum(resp_values), 2) if resp_values else None

    # Potential savings: estimate from overpriced/bundled flags
    flagged_charges = [
        item.charge_amount for item in line_items
        if any(f.type in ("price_inflated", "bundled_service") for f in item.flags)
    ]
    potential_savings = round(sum(flagged_charges) * random.uniform(0.08, 0.2), 2) if flagged_charges else None

    return Totals(
        billed=billed,
        allowed=allowed,
        insurance_paid=insurance_paid,
        patient_responsibility=patient_resp,
        potential_savings=potential_savings,
    )


def _build_denial_codes(line_items: list[LineItem], payer: dict) -> list[dict]:
    """Generate 1-3 denial codes tied to flagged line items."""
    flagged_items = [item for item in line_items if any(f.severity == "critical" for f in item.flags)]
    if not flagged_items:
        flagged_items = line_items[:2]

    num_denials = random.randint(1, min(3, len(flagged_items)))
    chosen = random.sample(flagged_items, num_denials)
    template_pool = random.sample(DENIAL_CODES, num_denials)

    denials: list[dict] = []
    for item, tpl in zip(chosen, template_pool):
        denials.append(
            {
                "code": tpl["code"],
                "reason": tpl["reason"],
                "severity": tpl["severity"],
                "amount": round(item.charge_amount * random.uniform(0.5, 1.0), 2),
                "line_item_id": item.id,
                "line_item_description": item.description,
                "cpt_hcpcs": item.cpt_hcpcs,
            }
        )
    return denials


def _build_appeal_prediction(denials: list[dict], line_items: list[LineItem]) -> AppealPrediction:
    """Generate appeal success probability and top factors."""
    critical_flags = [
        flag for item in line_items for flag in item.flags if flag.severity == "critical"
    ]
    has_price_flag = any(
        f.type == "price_inflated" for item in line_items for f in item.flags
    )
    has_code_flag = any(
        f.type == "billing_code_mismatch" for item in line_items for f in item.flags
    )

    base_probability = random.uniform(0.55, 0.78)
    if has_price_flag:
        base_probability += random.uniform(0.03, 0.08)
    if has_code_flag:
        base_probability -= random.uniform(0.05, 0.1)

    probability = round(max(0.25, min(0.95, base_probability)), 2)
    spread = round(random.uniform(0.03, 0.08), 2)

    top_factors = []
    if denials:
        top_factors.append(
            f"Denial code {denials[0]['code']} ({denials[0]['reason'][:60]}...) "
            "is commonly overturned when medical necessity is documented."
        )
    if has_price_flag:
        top_factors.append(
            "Charges exceed regional 75th percentile benchmarks, supporting "
            "renegotiation or consumer protection arguments."
        )
    if len(critical_flags) > 0:
        top_factors.append(
            f"{len(critical_flags)} critical billing errors detected, each "
            "representing a standalone appeal basis."
        )
    top_factors.append(
        "Complete clinical documentation with supporting ICD-10 diagnoses "
        "increases the likelihood of a favorable external review."
    )

    return AppealPrediction(
        success_probability=probability,
        confidence_interval=[
            round(probability - spread, 2),
            round(probability + spread, 2),
        ],
        top_factors=top_factors,
    )


def _build_explanation(denials: list[dict], appeal_prediction: AppealPrediction) -> str:
    """Generate a natural-language explanation of the analysis."""
    if not denials:
        return (
            "This bill contains no critical denials. Minor billing variations "
            "were identified but do not currently warrant an appeal. "
            "Monitoring is recommended."
        )

    primary = denials[0]
    code_flags = [d["code"] for d in denials]

    return (
        f"The primary denial is {primary['code']} — {primary['reason']} for "
        f"{primary.get('line_item_description', 'the service')} "
        f"({primary.get('cpt_hcpcs', 'N/A')}). "
        f"Additional denial codes present: {', '.join(code_flags)}. "
        f"We estimate a {appeal_prediction.success_probability:.0%} probability "
        f"of successful appeal based on medical necessity documentation, "
        f"regional charge benchmarks, and historical overturn rates for these "
        f"denial categories. {appeal_prediction.top_factors[0] if appeal_prediction.top_factors else ''}"
    )


def _build_letter(patient: dict, provider: dict, payer: dict, denials: list[dict], totals: Totals) -> Letter:
    """Generate a realistic markdown appeal letter."""
    if not denials:
        return Letter(
            status="draft",
            content_markdown=(
                "# Appeal Letter Not Required\n\n"
                "No critical denials were identified on this bill. "
                "No appeal letter is currently warranted."
            ),
            verified_fields=["no_denials"],
        )

    primary = denials[0]
    service_desc = primary.get("line_item_description", "the disputed service")
    cpt = primary.get("cpt_hcpcs", "N/A")

    content = f"""# Appeal Letter — {primary['code']} Denial

**Date:** {date.today().strftime('%B %d, %Y')}
**Re:** Claim {payer['claim_number']} — {primary['code']} Denial
**Patient:** {patient['name']} (Member ID: {patient['member_id']})
**Provider:** {provider['name']} (NPI: {provider['npi']})
**Amount in Dispute:** ${primary.get('amount', totals.patient_responsibility or 0):,.2f}

## Dear Claims Appeals Department,

I am writing to appeal the denial of coverage for **{service_desc}**
(CPT/HCPCS: **{cpt}**) on behalf of my client, **{patient['name']}**.

## Medical Necessity

The service was medically necessary given the patient's diagnosis and
clinical presentation. The treating provider's documentation, submitted
contemporaneously with the claim, clearly supports the level of service
rendered. The denial reason — *"{primary['reason']}"* — is not supported
by the medical record.

## Billing Accuracy

The procedural and diagnostic coding were accurate and consistent with
standard coding guidelines (CPT, ICD-10-CM, and NCCI). Any suggestion of
improper coding or lack of medical necessity is contradicted by the
attached clinical documentation.

## Request

We respectfully request that this claim be reprocessed and paid according
to the patient's benefits plan. If you disagree, please provide the
specific policy language or clinical documentation that supports your
position, as required by state and federal regulations.

Sincerely,

**Medical Bill Advocacy Team**
Provider: {provider['name']}
Phone: {provider['phone']}
"""

    verified_fields = [
        "patient_name",
        "patient_member_id",
        "provider_name",
        "provider_npi",
        "payer_name",
        "claim_number",
        f"denial_code_{primary['code']}",
        "service_description",
        "amount_in_dispute",
    ]

    return Letter(
        status="draft",  # verification happens in a later phase
        content_markdown=content,
        verified_fields=verified_fields,
    )


def generate_mock_parsed_bill(
    document_id: str,
    original_filename: str = "unknown.pdf",
    uploaded_at: datetime | None = None,
) -> ParsedBill:
    """
    Generate a complete, realistic ParsedBill for a document.

    This is the primary entry point used by the mock pipeline. It produces
    deterministic output (seeded per document) so re-runs are stable,
    while still looking organic.
    """
    # Seed the global RNG per document for deterministic, reproducible output
    seed = int(uuid.UUID(document_id).int % (2**32))
    random.seed(seed)

    patient = _random_choice(PATIENTS)
    provider = _random_choice(PROVIDERS)
    payer = _random_choice(PAYERS)

    # Random service date within the last 90 days
    service_date = date.today() - timedelta(days=random.randint(5, 90))

    line_items = _build_line_items(patient, provider)
    totals = _build_totals(line_items)
    denial_codes = _build_denial_codes(line_items, payer)
    appeal_prediction = _build_appeal_prediction(denial_codes, line_items)
    explanation = _build_explanation(denial_codes, appeal_prediction)
    letter = _build_letter(patient, provider, payer, denial_codes, totals)

    uploaded = uploaded_at or datetime.now(timezone.utc)

    return ParsedBill(
        document_id=document_id,
        status=DocumentStatus.letter_ready,
        uploaded_at=uploaded,
        source_type="ocr_extraction_v0_mock",
        patient={
            "name": patient["name"],
            "dob": patient["dob"],
            "gender": patient["gender"],
            "member_id": patient["member_id"],
            "address": patient["address"],
        },
        provider={
            "name": provider["name"],
            "npi": provider["npi"],
            "tax_id": provider["tax_id"],
            "address": provider["address"],
            "phone": provider["phone"],
        },
        payer={
            "name": payer["name"],
            "payer_id": payer["payer_id"],
            "phone": payer["phone"],
            "claim_number": payer["claim_number"],
        },
        service_date=service_date,
        line_items=line_items,
        totals=totals,
        denial_codes=denial_codes,
        appeal_prediction=appeal_prediction,
        explanation=explanation,
        letter=letter,
        audit={
            "extraction_engine": "mock-v1",
            "rules_engine": "rust-rules-v0 (mock)",
            "llm_engine": "mock-llm-v1",
            "extraction_confidence": round(random.uniform(0.82, 0.96), 4),
            "processing_ms": random.randint(800, 3500),
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_version": "0.1.0",
        },
    )