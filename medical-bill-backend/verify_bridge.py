"""
End-to-end verification of the Python↔Rust bridge contract.

Simulates the Rust service locally (since Rust compilation requires MSVC
build tools not present on this machine). Verifies:
  1. The rules subset extraction matches the precise Rust ParsedBill schema
  2. Flag merging preserves all non-rule fields (patient, provider, etc.)
  3. Graceful degradation when the service is unreachable
"""

import asyncio
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from app.config import settings
from app.services.mock_data import generate_mock_parsed_bill
from app.services import rules_engine


async def main() -> None:
    failures = []

    # 1. Generate a mock bill (deterministic per document_id)
    bill = generate_mock_parsed_bill(
        document_id="9e107d9d-372b-4c4f-8f4e-9f2a1b2c3d4e",
        original_filename="test-bill.pdf",
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    print(f"[OK] Generated mock bill: {len(bill.line_items)} line items")

    # 2. Verify subset extraction produces exact Rust schema
    payload = rules_engine._extract_rules_subset(bill)
    payload_json = payload.model_dump(mode="json")
    expected_keys = {"document_id", "status", "service_date", "line_items", "totals"}
    if set(payload_json.keys()) != expected_keys:
        failures.append(
            f"Subset keys mismatch: {set(payload_json.keys())} != {expected_keys}"
        )
    else:
        print(f"[OK] Rules subset has exact schema: {sorted(payload_json.keys())}")

    # Verify line item subset schema
    li_keys = set(payload_json["line_items"][0].keys())
    expected_li = {
        "id", "page", "description", "cpt_hcpcs", "icd10", "units",
        "charge_amount", "allowed_amount", "paid_amount",
        "patient_responsibility", "modifiers", "flags",
    }
    if li_keys != expected_li:
        failures.append(f"LineItem subset mismatch: {li_keys} != {expected_li}")
    else:
        print(f"[OK] LineItem subset has exact schema: {sorted(li_keys)}")

    # 3. Simulate Rust engine response: append deterministic flags
    #    (Rust `apply_rules` appends to existing `flags` vectors)
    simulated_response = {
        **payload_json,
        "line_items": [
            {
                **li,
                "flags": li["flags"] + [
                    {
                        "type": "math_error",
                        "severity": "high",
                        "message": "Amount mismatch: Expected patient responsibility ≈ $10.00, found $15.00 (difference $5.00)",
                        "rule_id": "MATH-RECON-001",
                        "shap_contribution": None,
                    }
                ],
            }
            for li in payload_json["line_items"]
        ],
    }

    enriched_payload = rules_engine._RulesBill.model_validate(simulated_response)
    print("[OK] Simulated Rust response parsed as _RulesBill")

    # 4. Verify merge preserves the full bill and applies new flags
    merged = rules_engine._merge_flags(bill, enriched_payload)
    if merged.document_id != bill.document_id:
        failures.append("document_id not preserved")
    if merged.patient != bill.patient:
        failures.append("patient data lost during merge")
    if merged.provider != bill.provider:
        failures.append("provider data lost during merge")
    if merged.payer != bill.payer:
        failures.append("payer data lost during merge")
    if merged.letter != bill.letter:
        failures.append("letter data lost during merge")
    if merged.appeal_prediction != bill.appeal_prediction:
        failures.append("appeal_prediction lost during merge")

    if len(bill.line_items) != len(merged.line_items):
        failures.append("line item count changed during merge")
    else:
        extra_flags = 0
        for orig, new in zip(bill.line_items, merged.line_items):
            if orig.id != new.id:
                failures.append(f"line item id mismatch: {orig.id} != {new.id}")
            diff = len(new.flags) - len(orig.flags)
            if diff < 0:
                failures.append(f"flags removed from {orig.id}: {diff}")
            extra_flags += max(diff, 0)
        if extra_flags == len(bill.line_items):
            print(f"[OK] Merge applied {extra_flags} deterministic flags, preserved all fields")
        else:
            failures.append(f"expected {len(bill.line_items)} new flags, got {extra_flags}")

    # 5. Verify graceful degradation when service is unreachable
    original_settings = settings.RULES_ENGINE_URL
    settings.RULES_ENGINE_URL = "http://localhost:59999"  # nothing listening
    settings.RULES_ENGINE_TIMEOUT_SECONDS = 0.5
    fallback = await rules_engine.apply_rules(bill)
    settings.RULES_ENGINE_URL = original_settings
    settings.RULES_ENGINE_TIMEOUT_SECONDS = 5.0

    if fallback is bill:
        print("[OK] Graceful degradation: unreachable service returns original bill")
    else:
        failures.append("fallback did not return the original bill object")

    # 6. Verify disabled path
    settings.RULES_ENGINE_ENABLED = False
    disabled = await rules_engine.apply_rules(bill)
    settings.RULES_ENGINE_ENABLED = True
    if disabled is bill:
        print("[OK] RULES_ENGINE_ENABLED=false skips the call entirely")
    else:
        failures.append("disabled path did not return the original bill")

    if failures:
        print("\n=== FAILURES ===")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)

    print("\n=== ALL BRIDGE CHECKS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())