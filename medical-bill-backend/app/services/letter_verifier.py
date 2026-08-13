"""
Verifies that an appeal letter (LLM-generated or user-edited) only cites
facts that actually exist in the source ParsedBill.

DESIGN: rather than trying to recover facts from unstructured prose with
loose regexes (which is inherently ambiguous — a bare 5-digit number could
be a CPT code, a ZIP code, or a patient's age), this verifier requires
every checkable fact to be *labeled* in the letter text: "CPT 99284",
"HCPCS G0463", "NPI 1234567893", "Denial CO-97". This is enforced on the
generation side (see letter_generator.py's updated STRICT_SYSTEM_PROMPT
and _template_letter) so both the LLM path and the deterministic-template
fallback produce text this verifier can check unambiguously.

Dollar amounts are the one fact class still scanned unlabeled, because
they appear too naturally in prose ("...totaling $1,240.00...") to force
a label without making letters read stiffly — the tradeoff there is
accepted risk, not an oversight (see the docstring on
`_check_dollar_amounts`).
"""

import re
from typing import List, Tuple

from app.schemas import ParsedBill


_CODE_RE = re.compile(
    r"\b(?:CPT|HCPCS)(?:/(?:CPT|HCPCS))?\s*:?\s*([A-Z]?\d{4,5})\b",
    re.IGNORECASE,
)

_NPI_RE = re.compile(r"\bNPI\s*:?\s*(\d{10})\b", re.IGNORECASE)

_DENIAL_CODE_RE = re.compile(r"\b(CO|PR|OA|CR)-\d{1,3}\b", re.IGNORECASE)

_AMOUNT_RE = re.compile(r"\$[\d,]+\.?\d*")


def verify_letter(bill: ParsedBill, letter_content: str) -> Tuple[bool, List[str], List[str]]:
    problems: List[str] = []
    verified: List[str] = []

    content = letter_content.replace("**", "").replace("__", "")
    content_lower = content.lower()

    _check_claim_number(bill, content_lower, verified)
    _check_service_date(bill, content_lower, verified)
    _check_codes(bill, content, verified, problems)
    _check_npi(bill, content, verified, problems)
    _check_denial_codes(bill, content, verified, problems)
    _check_dollar_amounts(bill, content, verified, problems)

    return len(problems) == 0, sorted(set(verified)), problems


def _check_claim_number(bill: ParsedBill, content_lower: str, verified: List[str]) -> None:
    claim_number = (bill.payer or {}).get("claim_number")
    if claim_number and str(claim_number).lower() in content_lower:
        verified.append("claim_number")


def _check_service_date(bill: ParsedBill, content_lower: str, verified: List[str]) -> None:
    if not bill.service_date:
        return
    variants = [
        bill.service_date.isoformat(),
        bill.service_date.strftime("%m/%d/%Y"),
        bill.service_date.strftime("%B %d, %Y"),
        bill.service_date.strftime("%b %d, %Y"),
    ]
    if any(v.lower() in content_lower for v in variants):
        verified.append("service_date")


def _check_codes(bill: ParsedBill, content: str, verified: List[str], problems: List[str]) -> None:
    known_codes = {item.cpt_hcpcs.upper() for item in bill.line_items if item.cpt_hcpcs}

    for match in _CODE_RE.finditer(content):
        code = match.group(1).upper()
        if code in known_codes:
            verified.append(f"code_{code}")
        else:
            problems.append(
                f"Code '{code}' is cited as a CPT/HCPCS code in the letter but "
                f"does not appear in the bill's line items."
            )


def _check_npi(bill: ParsedBill, content: str, verified: List[str], problems: List[str]) -> None:
    known_npi = str((bill.provider or {}).get("npi", "")).strip()

    for match in _NPI_RE.finditer(content):
        npi = match.group(1)
        if known_npi and npi == known_npi:
            verified.append("provider_npi")
        else:
            problems.append(
                f"NPI '{npi}' is cited in the letter but does not match the "
                f"provider's NPI on the bill."
            )


def _check_denial_codes(bill: ParsedBill, content: str, verified: List[str], problems: List[str]) -> None:
    known_denials = {
        str(d.get("code", "")).upper() for d in (bill.denial_codes or []) if d.get("code")
    }

    for match in _DENIAL_CODE_RE.finditer(content):
        code = match.group(0).upper()
        if code in known_denials:
            verified.append(f"denial_{code}")
        else:
            problems.append(
                f"Denial code '{code}' is cited in the letter but does not "
                f"appear in the bill's denial codes."
            )


def _check_dollar_amounts(bill: ParsedBill, content: str, verified: List[str], problems: List[str]) -> None:
    """Unlike codes/NPI/denials, dollar amounts are intentionally NOT
    required to carry a label — "totaling $1,240.00 for the visit" reads
    naturally and forcing a label here would make every letter stilted.
    The accepted tradeoff: a dollar figure that happens to equal a real
    line-item amount but is used in an unrelated/wrong context (rare, and
    not something regex matching can resolve without full NLU) won't be
    caught. Every DIFFERING dollar figure — the actual hallucination
    failure mode we've observed — still is.
    """
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

    for raw in _AMOUNT_RE.findall(content):
        try:
            value = round(float(raw.replace("$", "").replace(",", "")), 2)
        except ValueError:
            continue
        if value == 0 or value in known_amounts:
            verified.append(f"amount_{value}")
        else:
            problems.append(f"Amount {raw} doesn't match any known figure on the bill")