import re
from typing import List, Tuple
from app.schemas import ParsedBill

def verify_letter(bill: ParsedBill, letter_content: str) -> Tuple[bool, List[str], List[str]]:
    problems: List[str] = []
    verified: List[str] = []
    content_lower = letter_content.lower()

    claim_number = (bill.payer or {}).get("claim_number")
    if claim_number and claim_number.lower() in content_lower:
        verified.append("claim_number")

    if bill.service_date:
        variants = [
            bill.service_date.isoformat(),
            bill.service_date.strftime("%m/%d/%Y"),
            bill.service_date.strftime("%B %d, %Y"),
            bill.service_date.strftime("%b %d, %Y"),
        ]
        if any(v.lower() in content_lower for v in variants):
            verified.append("service_date")

    known_cpts = {item.cpt_hcpcs for item in bill.line_items if item.cpt_hcpcs}
    for code in set(re.findall(r"\b\d{5}\b", letter_content)):
        if code in known_cpts:
            verified.append(f"cpt_{code}")
        else:
            problems.append(f"CPT code {code} appears in the letter but is not in the bill")

    known_amounts = set()
    for item in bill.line_items:
        known_amounts.add(round(item.charge_amount, 2))
        for f in ("allowed_amount", "paid_amount", "patient_responsibility"):
            v = getattr(item, f, None)
            if v is not None:
                known_amounts.add(round(v, 2))
    if bill.totals:
        for f in ("billed", "allowed", "insurance_paid", "patient_responsibility", "potential_savings"):
            v = getattr(bill.totals, f, None)
            if v is not None:
                known_amounts.add(round(v, 2))

    for raw in re.findall(r"\$[\d,]+\.?\d*", letter_content):
        try:
            value = round(float(raw.replace("$", "").replace(",", "")), 2)
        except ValueError:
            continue
        if value == 0 or value in known_amounts:
            verified.append(f"amount_{value}")
        else:
            problems.append(f"Amount {raw} doesn't match any known figure on the bill")

    return len(problems) == 0, sorted(set(verified)), problems