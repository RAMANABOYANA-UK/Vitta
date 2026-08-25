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

The one exception is HCPCS-style codes (letter + 4 digits, e.g. "G0463"):
a bare letter+4-digit token in prose is unambiguous enough to scan
unlabeled, because ZIP codes and ages are numeric-only.

Dollar amounts are the one fact class still scanned unlabeled, because
they appear too naturally in prose ("...totaling $1,240.00...") to force
a label without making letters read stiffly — the tradeoff there is
accepted risk, not an oversight (see the docstring on
`_check_dollar_amounts`).
"""

import re
from typing import List, Tuple

from app.config import settings
from app.schemas import ParsedBill


_CODE_RE = re.compile(
    r"\b(?:CPT|HCPCS)(?:/(?:CPT|HCPCS))?\s*:?\s*([A-Z]?\d{4,5})\b",
    re.IGNORECASE,
)

# Unlabeled HCPCS-style codes: letter + 4 digits (e.g., G0463, J3490).
# Unambiguous because ZIP codes and ages are numeric-only.
_UNLABELED_HCPCS_RE = re.compile(r"\b[A-Z]\d{4}\b", re.IGNORECASE)

_NPI_RE = re.compile(r"\bNPI\s*:?\s*(\d{10})\b", re.IGNORECASE)

# CARC (Claim Adjustment Reason Code): CO-97, PR-4, OA-23, CR-1
# RARC (Remittance Advice Remark Code): N362, M15, MA01 (letter + digits, no hyphen)
_DENIAL_CODE_RE = re.compile(
    r"\b(?:CO|PR|OA|CR)-\d{1,3}\b|\bN\d{3}\b",
    re.IGNORECASE,
)

_AMOUNT_RE = re.compile(r"\$[\d,]+\.?\d*")

# Legal/regulatory citation patterns (U.S.C., C.F.R., U.S. Stat.). Fabricated
# references here are the highest-liability failure mode in the system, so when
# CITATION_FABRICATION_POLICY != "off" they are checked against an allow-list
# and fail verification if not approved.
_CITATION_RE = re.compile(
    r"\b\d{1,3}\s*(?:U\.?\s?S\.?\s?C\.?\s*§?\s*\.?\d+|C\.?\s?F\.?\s?R\.?\s*§?\s*\.?\d+|U\.?\s?S\.?\s?Stat\.?\s*\.?\d+)",
    re.IGNORECASE,
)


def _allowed_citations() -> set[str]:
    """Parse the configured comma-separated allow-list into lowercased strings."""
    raw = getattr(settings, "ALLOWED_CITATIONS", "") or ""
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def verify_letter(bill: ParsedBill, letter_content: str) -> Tuple[bool, List[str], List[str]]:
    problems: List[str] = []
    verified: List[str] = []

    content = letter_content.replace("**", "").replace("__", "")
    content_lower = content.lower()

    _check_claim_number(bill, content_lower, verified, problems)
    _check_service_date(bill, content_lower, verified, problems)
    _check_codes(bill, content, verified, problems)
    _check_npi(bill, content, verified, problems)
    _check_denial_codes(bill, content, verified, problems)
    _check_dollar_amounts(bill, content, verified, problems)
    _check_citations(bill, content, problems)

    return len(problems) == 0, sorted(set(verified)), problems


def _check_claim_number(
    bill: ParsedBill,
    content_lower: str,
    verified: List[str],
    problems: List[str],
) -> None:
    """Claim number must appear in the letter — a real appeal always cites it."""
    claim_number = (bill.payer or {}).get("claim_number")
    if claim_number:
        if str(claim_number).lower() in content_lower:
            verified.append("claim_number")
        else:
            problems.append(f"Claim number {claim_number} missing from letter")


def _check_service_date(
    bill: ParsedBill,
    content_lower: str,
    verified: List[str],
    problems: List[str],
) -> None:
    """Service date must appear in the letter in at least one common format."""
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
    else:
        problems.append(
            f"Service date {bill.service_date.isoformat()} missing from letter"
        )


def _check_codes(
    bill: ParsedBill,
    content: str,
    verified: List[str],
    problems: List[str],
) -> None:
    known_codes = {item.cpt_hcpcs.upper() for item in bill.line_items if item.cpt_hcpcs}
    checked_codes: set[str] = set()

    # Labeled codes: "CPT 99284", "HCPCS G0463", "CPT/HCPCS 99284"
    for match in _CODE_RE.finditer(content):
        code = match.group(1).upper()
        if code in checked_codes:
            continue
        checked_codes.add(code)
        if code in known_codes:
            verified.append(f"code_{code}")
        else:
            problems.append(
                f"Code '{code}' is cited as a CPT/HCPCS code in the letter but "
                f"does not appear in the bill's line items."
            )

    # Unlabeled HCPCS-style codes (letter + 4 digits) — unambiguous because
    # ZIP codes and ages are numeric-only. A bare "G0463" in prose is almost
    # certainly a procedure code.
    for match in _UNLABELED_HCPCS_RE.finditer(content):
        code = match.group(0).upper()
        if code in checked_codes:
            continue
        checked_codes.add(code)
        if code in known_codes:
            verified.append(f"code_{code}")
        else:
            problems.append(
                f"Code '{code}' appears in the letter but is not on the bill."
            )


def _check_npi(
    bill: ParsedBill,
    content: str,
    verified: List[str],
    problems: List[str],
) -> None:
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


def _check_denial_codes(
    bill: ParsedBill,
    content: str,
    verified: List[str],
    problems: List[str],
) -> None:
    """Verify denial codes cited in the letter against the bill.

    Denial codes can appear under multiple field names in the source data:
    - `code` (Vitta contract)
    - `carc` (Claim Adjustment Reason Code — standard X12/837 format)
    - `rarc` (Remittance Advice Remark Code — standard X12/835 format)

    We collect all of them so the verifier is robust to whichever shape
    Member 2 (or a future EOB parser) returns.
    """
    known_denials: set[str] = set()
    for d in (bill.denial_codes or []):
        for field in ("code", "carc", "rarc"):
            val = d.get(field)
            if val:
                known_denials.add(str(val).upper())

    for match in _DENIAL_CODE_RE.finditer(content):
        code = match.group(0).upper()
        if code in known_denials:
            verified.append(f"denial_{code}")
        else:
            problems.append(
                f"Denial code '{code}' is cited in the letter but does not "
                f"appear in the bill's denial codes."
            )


def _check_dollar_amounts(
    bill: ParsedBill,
    content: str,
    verified: List[str],
    problems: List[str],
) -> None:
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
def _check_citations(
    bill: ParsedBill,
    content: str,
    problems: List[str],
) -> None:
    """Fail-closed citation guard (see CITATION_FABRICATION_POLICY).

    The letter verifier historically checked codes, dates, NPIs and amounts but
    NEVER statutory/regulatory citations — so a fabricated "42 U.S.C. 1395" or a
    hallucinated appeal-deadline statute went out unchallenged. When the policy is
    "warn", any citation that is NOT in the approved allow-list fails verification,
    so the letter is marked unverified until the text is corrected (or the citation
    is added to the approved library after genuine review).

    Resolution of the roadmap's "unresolved question": we choose the allow-list
    constraint (option: constrain letters to pre-approved citation strings), with
    the ability to omit citations simply by leaving ALLOWED_CITATIONS empty while
    policy is "warn" — in which case any citation is rejected (de-facto "no
    citations in generated text", the safest option).
    """
    policy = (getattr(settings, "CITATION_FABRICATION_POLICY", "off") or "off").lower()
    if policy == "off":
        return

    allowed = _allowed_citations()
    seen: set[str] = set()
    for match in _CITATION_RE.finditer(content):
        citation = " ".join(match.group(0).split()).strip()
        key = citation.lower()
        if key in seen:
            continue
        seen.add(key)
        if not any(key in a or a in key for a in allowed):
            problems.append(
                f"Citation '{citation}' could not be verified against the approved "
                f"reference library. Legal/regulatory citations must come from the "
                f"approved list or be removed from the letter."
            )