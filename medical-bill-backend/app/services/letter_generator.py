import json
import logging
import httpx
from app.config import settings
from app.schemas import Letter, ParsedBill
from app.services.letter_verifier import verify_letter

logger = logging.getLogger(__name__)

STRICT_SYSTEM_PROMPT = """You are an expert medical billing advocate. Write a professional, concise appeal letter.

STRICT RULES:
1. Only use information explicitly present in the structured data provided.
2. Never invent CPT codes, dollar amounts, dates, claim numbers, member IDs, provider names, or NPIs.
3. If a value is missing, omit it — don't use placeholders.
4. Focus only on the flagged issues.
5. Be factual, calm, professional. No legal threats.
6. Output only the letter body in clean Markdown, no code blocks, no commentary.
7. Start with a "Re:" reference line.
8. LABELING (required — the letter is programmatically verified against this exact format):
   - Every procedure code must be written as "CPT <code>" or "HCPCS <code>" —
     never write a bare code number with no label.
   - The provider's NPI, if mentioned, must be written as "NPI <number>".
   - Any denial code, if mentioned, must be written exactly as it appears in
     the source data (e.g. "CO-97", "PR-1") — don't reformat or abbreviate it.
   - Do not label unrelated numbers (ZIP codes, phone numbers, ages) as CPT,
     HCPCS, or NPI under any circumstances — only use those labels for
     actual procedure codes and the actual provider NPI."""

async def generate_appeal_letter(bill: ParsedBill) -> Letter:
    if not settings.LLM_ENABLED or not settings.LLM_API_KEY:
        return _template_letter(bill)

    for attempt in range(1, settings.LLM_MAX_RETRIES + 2):
        try:
            content = await _call_llm(bill)
        except Exception:
            logger.exception("LLM call failed (attempt %d)", attempt)
            continue

        is_valid, verified_fields, problems = verify_letter(bill, content)
        if is_valid:
            return Letter(
                status="draft",
                content_markdown=content,
                verified_fields=verified_fields,
                verification_passed=True,
                problems=[],
            )
        logger.warning("Letter failed verification (attempt %d) | problems=%s", attempt, problems)

    return _template_letter(bill, note="LLM output failed verification — safe template used")

async def _call_llm(bill: ParsedBill) -> str:
    if settings.LLM_PROVIDER == "openai":
        return await _call_openai(bill)
    elif settings.LLM_PROVIDER == "anthropic":
        return await _call_anthropic(bill)
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}")

def _build_user_prompt(bill: ParsedBill) -> str:
    payload = {
        "claim_number": (bill.payer or {}).get("claim_number"),
        "service_date": bill.service_date.isoformat() if bill.service_date else None,
        "patient": bill.patient, "provider": bill.provider, "payer": bill.payer,
        "totals": bill.totals.model_dump() if bill.totals else None,
        "denial_codes": bill.denial_codes,
        "flagged_line_items": [
            {"description": i.description, "cpt_hcpcs": i.cpt_hcpcs, "charge_amount": i.charge_amount,
             "allowed_amount": i.allowed_amount, "patient_responsibility": i.patient_responsibility,
             "flags": [f.model_dump() for f in i.flags]}
            for i in bill.line_items if i.flags
        ],
        "explanation": bill.explanation,
    }
    return "Write an appeal letter using ONLY this data:\n\n" + json.dumps(payload, indent=2, default=str)

async def _call_openai(bill: ParsedBill) -> str:
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": settings.LLM_MODEL, "temperature": 0.2,
        "messages": [{"role": "system", "content": STRICT_SYSTEM_PROMPT},
                     {"role": "user", "content": _build_user_prompt(bill)}],
    }
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
        resp = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

async def _call_anthropic(bill: ParsedBill) -> str:
    headers = {"x-api-key": settings.LLM_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    payload = {
        "model": settings.LLM_MODEL, "max_tokens": 1200,
        "system": STRICT_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": _build_user_prompt(bill)}],
    }
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
        resp = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return "".join(b.get("text", "") for b in data.get("content", [])).strip()

def _template_letter(bill: ParsedBill, note: str = "") -> Letter:
    claim = (bill.payer or {}).get("claim_number")
    service_date = bill.service_date.isoformat() if bill.service_date else None
    patient_name = (bill.patient or {}).get("name", "the undersigned")
    flagged = [i for i in bill.line_items if i.flags]
    lines = [f"- {i.description} (CPT {i.cpt_hcpcs}): {f.message}" for i in flagged for f in i.flags]
    issues_text = "\n".join(lines) if lines else "- Please re-evaluate the flagged charges on this claim."
    ref_line = f"Re: Appeal of Claim {claim}" if claim else "Re: Appeal of Medical Bill"
    date_line = f"for services rendered on {service_date}" if service_date else "as detailed below"

    content = f"""{ref_line}

Dear Claims Review Department,

I am writing to appeal the processing of this claim {date_line}.

After reviewing the bill and Explanation of Benefits, I have identified the following issues:

{issues_text}

I respectfully request that these items be reprocessed and any resulting overcharges corrected.

Thank you for your attention to this matter.

Sincerely,
{patient_name}"""

    if note:
        content += f"\n\n<!-- {note} -->"
    is_valid, verified_fields, problems = verify_letter(bill, content)
    return Letter(
        status="draft",
        content_markdown=content.strip(),
        verified_fields=verified_fields,
        verification_passed=is_valid,
        problems=problems,
    )