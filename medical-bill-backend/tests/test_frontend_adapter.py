"""
Contract-conformance tests for app/services/frontend_adapter.py.

Runs WITHOUT pytest / fastapi / sqlmodel (none are installable in the sandbox):
the adapter is dependency-free, so we load it directly from its file path and
drive it with a plain dict fixture shaped exactly like
``ParsedBill.model_dump(mode="json")``.

    python3 medical-bill-backend/tests/test_frontend_adapter.py

Exit code 0 = all checks passed; 1 = at least one failed.
"""

import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Load the adapter module directly from its file (no package import needed).
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ADAPTER_PATH = os.path.join(_HERE, "..", "app", "services", "frontend_adapter.py")
_spec = importlib.util.spec_from_file_location("frontend_adapter", _ADAPTER_PATH)
adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(adapter)


# ---------------------------------------------------------------------------
# Tiny assertion harness
# ---------------------------------------------------------------------------
_failures = []
_checks = 0


def check(cond, msg):
    global _checks
    _checks += 1
    if not cond:
        _failures.append(msg)
        print("  FAIL: {}".format(msg))


def is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# ---------------------------------------------------------------------------
# Fixture: a realistic result_json (what documents.py stores).
# Includes an adjudicated line, a SECOND adjudicated line with multiple flags
# (to exercise dedup), and a fully-DENIED line (allowed/paid None) to prove the
# reconciliation logic does not false-alarm.
# ---------------------------------------------------------------------------
def make_result():
    return {
        "document_id": "11111111-1111-4111-8111-111111111111",
        "status": "letter_ready",
        "uploaded_at": "2026-08-20T10:00:00+00:00",
        "source_type": "ocr_extraction_v0_mock",
        "patient": {
            "name": "Sarah Mitchell",
            "dob": "1985-06-12",
            "gender": "F",
            "member_id": "M-100234-01",
            "address": "482 Oakwood Drive, Portland, OR 97205",
        },
        "provider": {
            "name": "Northside Medical Center",
            "npi": "1234567890",
            "tax_id": "93-1234567",
            "address": "900 Health Sciences Blvd, Portland, OR 97239",
            "phone": "(503) 555-0134",
        },
        "payer": {
            "name": "BlueCross BlueShield of Oregon",
            "payer_id": "80068",
            "phone": "(800) 555-0100",
            "claim_number": "GX-2025-883241",
        },
        "service_date": "2026-07-15",
        "line_items": [
            {
                "id": "LI-1-ABCD1234",
                "page": 1,
                "description": "Emergency department visit, level 4",
                "cpt_hcpcs": "99284",
                "icd10": ["I10", "R10.9"],
                "units": 1.0,
                "charge_amount": 1250.00,
                "allowed_amount": 800.00,
                "paid_amount": 640.00,
                "patient_responsibility": 160.00,  # 800 == 640 + 160  -> consistent
                "modifiers": ["25"],
                "flags": [
                    {
                        "type": "price_inflated",
                        "severity": "warning",
                        "message": "Charge of $1,250.00 is 40% above the 75th percentile for CPT 99284 in this region.",
                        "rule_id": "RULE-PRICE-001",
                        "shap_contribution": 0.32,
                    },
                    {
                        "type": "billing_code_mismatch",
                        "severity": "critical",
                        "message": "CPT 99284 appears inconsistent with documented ICD-10 codes I10, R10.9.",
                        "rule_id": "RULE-CODE-017",
                        "shap_contribution": 0.51,
                    },
                ],
            },
            {
                "id": "LI-2-EEFF5678",
                "page": 1,
                "description": "CT scan of abdomen and pelvis with contrast",
                "cpt_hcpcs": "74177",
                "icd10": ["K57.30"],
                "units": 1.0,
                "charge_amount": 2850.00,
                "allowed_amount": 1500.00,
                "paid_amount": 1200.00,
                "patient_responsibility": 300.00,  # 1500 == 1200 + 300 -> consistent
                "modifiers": [],
                "flags": [
                    {
                        "type": "bundled_service",
                        "severity": "info",
                        "message": "Service may be eligible for bundling under National Correct Coding Initiative (NCCI) edits.",
                        "rule_id": "RULE-NCCI-023",
                        "shap_contribution": 0.12,
                    }
                ],
            },
            {
                "id": "LI-3-DENIED00",
                "page": 2,
                "description": "MRI brain without contrast",
                "cpt_hcpcs": "J1200",  # HCPCS shape: letter + 4 digits
                "icd10": [],
                "units": 1.0,
                "charge_amount": 3200.00,
                "allowed_amount": None,   # fully denied
                "paid_amount": None,
                "patient_responsibility": 3200.00,
                "modifiers": [],
                "flags": [],
            },
        ],
        "totals": {
            "billed": 7300.00,
            "allowed": 2300.00,
            "insurance_paid": 1840.00,
            "patient_responsibility": 3660.00,
            "potential_savings": 410.00,
        },
        "denial_codes": [
            {
                "code": "CO-97",
                "reason": "The service or procedure was not medically necessary.",
                "severity": "critical",
                "amount": 2850.00,
                "line_item_id": "LI-2-EEFF5678",
                "line_item_description": "CT scan of abdomen and pelvis with contrast",
                "cpt_hcpcs": "74177",
            }
        ],
        "appeal_prediction": {
            "success_probability": 0.71,
            "confidence_interval": [0.66, 0.76],
            "top_factors": [
                "Denial code CO-97 is commonly overturned when medical necessity is documented.",
                "Charges exceed regional 75th percentile benchmarks.",
            ],
            "model_version": None,
        },
        "explanation": "The primary denial is CO-97 for the CT scan (74177).",
        "letter": {
            "status": "draft",
            "content_markdown": "# Appeal Letter\n\nBody text.",
            "verified_fields": ["patient_name", "claim_number"],
            "verification_passed": False,
            "problems": [],
        },
        "audit": {
            "pipeline_version": "0.3.0",
            "extraction_path": "mock",
            "completed_at": "2026-08-20T10:00:05+00:00",
        },
    }


VALID_SEVERITIES = {"low", "medium", "high"}
VALID_CATEGORIES = {
    "duplicate_charge", "unbundling", "arithmetic_mismatch", "invalid_deprecated_code",
    "surprise_billing", "pricing_anomaly", "upcoding", "denied_claim",
    "missing_authorization", "coverage_gap",
}
VALID_STAGE_STATUS = {"pending", "running", "done", "failed", "skipped"}
VALID_JOB_STATUS = {
    "uploading", "preprocessing", "ocr_running", "extraction_running",
    "validation_running", "ml_scoring_running", "done", "failed",
}


# ---------------------------------------------------------------------------
def test_bill():
    print("to_frontend_bill")
    r = make_result()
    b = adapter.to_frontend_bill(r)

    check(b["documentId"] == r["document_id"], "documentId echoes document_id")
    check(b["jobId"] == r["document_id"], "jobId mirrors document_id")

    m = b["metadata"]
    check(m["provider"] == "Northside Medical Center", "metadata.provider <- provider.name")
    check(m["providerNpi"] == "1234567890", "metadata.providerNpi <- provider.npi")
    check(m["payer"] == "BlueCross BlueShield of Oregon", "metadata.payer <- payer.name")
    check(m["statementDate"] == "2026-07-15", "metadata.statementDate <- service_date")
    check(m["accountRef"] == "GX-2025-883241", "metadata.accountRef <- payer.claim_number")
    check(m["memberName"] == "Sarah Mitchell", "metadata.memberName <- patient.name")
    check(m["memberId"] == "M-100234-01", "metadata.memberId <- patient.member_id")
    check(m["patientLiability"] == 3660.00, "metadata.patientLiability <- totals.patient_responsibility")

    t = b["totals"]
    check(t["billed"] == 7300.00, "totals.billed")
    check(t["allowed"] == 2300.00, "totals.allowed")
    check(t["paid"] == 1840.00, "totals.paid <- insurance_paid (RENAME)")
    check(t["patientResponsibility"] == 3660.00, "totals.patientResponsibility")

    # Reconciliation: both adjudicated lines are internally consistent; the
    # denied line is skipped -> ok must be True (no false alarm).
    rec = t["reconciliation"]
    check(rec["ok"] is True, "reconciliation.ok True when adjudicated lines are consistent")
    check(not rec["diff"], "reconciliation.diff falsy (0.0/None) when ok -> no diff rendered")

    check(isinstance(b["lineItems"], list) and len(b["lineItems"]) == 3, "lineItems is a 3-element array")
    li0 = b["lineItems"][0]
    check(li0["bbox"] is None, "lineItem.bbox is None (no OCR)")
    check(li0["serviceDate"] == "2026-07-15", "lineItem.serviceDate <- bill service_date")
    check(li0["cptCode"] == "99284" and li0["codeType"] == "CPT", "CPT code detected (5 digits)")
    check(li0["hcpcsCode"] is None, "CPT line has no hcpcsCode")
    check(li0["amounts"]["charge"] == 1250.00, "lineItem.amounts.charge")
    check(li0["amounts"]["paid"] == 640.00, "lineItem.amounts.paid <- paid_amount")
    check(isinstance(li0["icdCodes"], list) and li0["icdCodes"][0]["code"] == "I10",
          "icdCodes are [{code, description}]")
    check(li0["verification"]["amounts"]["method"] == "absent", "verification method 'absent' (honest)")

    li2 = b["lineItems"][2]
    check(li2["hcpcsCode"] == "J1200" and li2["codeType"] == "HCPCS", "HCPCS code detected (letter+4 digits)")
    check(li2["cptCode"] is None, "HCPCS line has no cptCode")

    check(b["pages"] == [], "pages is empty (no OCR)")
    check(b["extractionWarnings"] == [], "extractionWarnings empty")
    check(b["extractionStatus"] == "complete", "extractionStatus complete when line items present")

    # Extraction mode drives the degraded-mode banner. Fixture audit path is
    # "mock" -> "sample" (data was synthesized, not read from the upload).
    check(b["extractionMode"] == "sample", "extractionMode 'sample' when extraction_path == mock")

    # textExtractionMethod honestly surfaces HOW the raw text was produced.
    check(b["textExtractionMethod"] is None, "textExtractionMethod None when not recorded")
    r_tex = make_result()
    r_tex["audit"]["text_extraction"] = {"method": "pdf_text", "layout_json": {"engine": "pypdf"}}
    check(adapter.to_frontend_bill(r_tex)["textExtractionMethod"] == "pdf_text",
          "textExtractionMethod 'pdf_text' when audit records it")

    # A real extraction path surfaces as "live" (no banner).
    r_live = make_result()
    r_live["audit"]["extraction_path"] = "member2"
    check(adapter.to_frontend_bill(r_live)["extractionMode"] == "live",
          "extractionMode 'live' when extraction_path == member2")
    # Unknown / missing path makes no claim either way.
    r_unknown = make_result()
    r_unknown["audit"]["extraction_path"] = None
    check(adapter.to_frontend_bill(r_unknown)["extractionMode"] is None,
          "extractionMode None when extraction_path is unknown")

    # Letter passthrough (camelCased for the frontend)
    check(b["letter"] is not None and b["letter"]["contentMarkdown"].startswith("# Appeal"),
          "letter.contentMarkdown passthrough")
    check(b["letter"]["verificationPassed"] is False, "letter.verificationPassed passthrough")


def test_reconciliation_mismatch():
    print("to_frontend_bill — reconciliation genuine mismatch")
    r = make_result()
    # Break the invariant on line 1: allowed 800 != 640 + 200
    r["line_items"][0]["patient_responsibility"] = 200.00
    b = adapter.to_frontend_bill(r)
    rec = b["totals"]["reconciliation"]
    check(rec["ok"] is False, "reconciliation.ok False on a real per-line mismatch")
    check(is_number(rec["diff"]) and rec["diff"] > 0, "reconciliation.diff is a positive number on mismatch")


def test_flagset():
    print("to_frontend_flagset")
    r = make_result()
    fs = adapter.to_frontend_flagset(r)

    check(isinstance(fs["flags"], list), "flags is always an array")
    # 2 line flags on LI-1 + 1 on LI-2 + 1 denial = 4
    check(len(fs["flags"]) == 4, "flag count = 3 line flags + 1 denial")

    for f in fs["flags"]:
        check(f["category"] in VALID_CATEGORIES, "flag.category in enum ({})".format(f.get("category")))
        check(f["severity"] in VALID_SEVERITIES, "flag.severity in enum ({})".format(f.get("severity")))
        check(f["detectionType"] in ("rule", "ml"), "flag.detectionType rule|ml")
        check(isinstance(f["lineItemIds"], list), "flag.lineItemIds is a list")
        check("contributions" in f["why"] and isinstance(f["why"]["contributions"], list),
              "flag.why.contributions is a list")
        check(f["evidence"]["codeReference"] is None, "evidence.codeReference is None (no fabricated citation)")
        check(f["confidence"] is None, "flag.confidence is None (frontend defaults it)")

    # Category mapping spot-checks
    cats = {f["title"]: f["category"] for f in fs["flags"]}
    check(cats.get("Price Inflated") == "pricing_anomaly", "price_inflated -> pricing_anomaly")
    check(cats.get("Billing Code Mismatch") == "invalid_deprecated_code", "billing_code_mismatch -> invalid_deprecated_code")
    check(cats.get("Bundled Service") == "unbundling", "bundled_service -> unbundling")
    denial_flags = [f for f in fs["flags"] if f["category"] == "denied_claim"]
    check(len(denial_flags) == 1, "denial -> one denied_claim flag")

    s = fs["summary"]
    check(set(s["countByCategory"].keys()) == VALID_CATEGORIES, "countByCategory has ALL 10 keys")
    check(s["countByCategory"]["pricing_anomaly"] == 1, "count pricing_anomaly == 1")
    check(s["countByCategory"]["denied_claim"] == 1, "count denied_claim == 1")
    check(s["ruleCount"] + s["mlCount"] == 4, "ruleCount + mlCount == total flags")
    # totalFlaggedAmount dedups by line: LI-1 (1250, two flags) counted once,
    # LI-2 (2850, flag + denial on same line) counted once -> 4100.
    check(s["totalFlaggedAmount"] == 4100.00,
          "totalFlaggedAmount dedups per line (got {})".format(s["totalFlaggedAmount"]))


def test_appeal_score():
    print("to_frontend_appeal_score")
    r = make_result()
    sc = adapter.to_frontend_appeal_score(r)

    check(sc["score"] == 0.71, "score <- success_probability")
    check(is_number(sc["sampleSize"]), "sampleSize is numeric (required by app.js toLocaleString)")
    check(sc["sampleSize"] == 0, "sampleSize defaults to 0 (no corpus)")
    check(sc["calibrated"] is False, "calibrated False (heuristic)")
    check(sc["confidenceInterval"] == [0.66, 0.76], "confidenceInterval passthrough")
    check(sc["calibration"] is None, "calibration None (guarded by app.js)")
    # Qualitative strings -> factors folded into basis, factors == []
    check(sc["factors"] == [], "factors [] when only qualitative strings (no invented impact)")
    check("commonly overturned" in sc["basis"], "qualitative factors preserved in basis")

    # Structured factors (future model) pass through with NUMERIC impact.
    r2 = make_result()
    r2["appeal_prediction"]["top_factors"] = [
        {"key": "denial_overturn_rate", "label": "Denial overturn rate", "impact": 0.22,
         "direction": "up", "description": "Historically overturned", "actionable": True}
    ]
    sc2 = adapter.to_frontend_appeal_score(r2)
    check(len(sc2["factors"]) == 1, "structured factor passes through")
    check(is_number(sc2["factors"][0]["impact"]), "passthrough factor impact is numeric")

    # Missing appeal_prediction -> safe empty score
    r3 = make_result()
    r3["appeal_prediction"] = None
    sc3 = adapter.to_frontend_appeal_score(r3)
    check(sc3["score"] is None and sc3["sampleSize"] == 0 and sc3["factors"] == [],
          "missing appeal_prediction -> safe empty score")


def test_pipeline_status():
    print("to_pipeline_status")
    r = make_result()

    # letter_ready with a stored result -> done + embedded partials
    ps = adapter.to_pipeline_status(r["document_id"], "letter_ready", None, r)
    check(ps["status"] == "done", "letter_ready -> done")
    check(ps["progress"] == 100, "done progress 100")
    check(ps["failure"] is None, "no failure on success")
    check(ps["partial"] is True, "partial True when result present")
    check(ps["partialBill"] is not None, "partialBill embedded")
    check(isinstance(ps["partialBill"]["lineItems"], list),
          "partialBill.lineItems is an array (app.js reads .length unguarded)")
    check(isinstance(ps["partialFlags"]["flags"], list),
          "partialFlags.flags is an array (app.js reads .length unguarded)")
    check(ps["partialScore"] is not None, "partialScore embedded")
    for st in ps["stages"]:
        check(st["status"] in VALID_STAGE_STATUS, "stage.status in enum ({})".format(st.get("status")))
        check(st["name"] in VALID_JOB_STATUS, "stage.name in enum ({})".format(st.get("name")))
    # mock extraction_path -> OCR stages skipped (honest)
    ocr = [s for s in ps["stages"] if s["name"] == "ocr_running"][0]
    check(ocr["status"] == "skipped", "ocr_running skipped in mock extraction mode")

    # processing, no result yet -> running status, no partials
    ps2 = adapter.to_pipeline_status(r["document_id"], "processing", None, None)
    check(ps2["status"] in VALID_JOB_STATUS and ps2["status"] not in ("done", "failed"),
          "processing -> a running status")
    check(ps2["partial"] is False, "partial False when no result")
    check(ps2["partialBill"] is None and ps2["partialFlags"] is None and ps2["partialScore"] is None,
          "no partials when no result")

    # error -> failed + failure object
    ps3 = adapter.to_pipeline_status(r["document_id"], "error", "boom", None)
    check(ps3["status"] == "failed", "error -> failed")
    check(ps3["failure"] and ps3["failure"]["message"] == "boom", "failure.message from error_message")
    failed_stage = [s for s in ps3["stages"] if s["status"] == "failed"]
    check(len(failed_stage) >= 1, "at least one stage marked failed on error")

    # uploaded -> uploading
    ps4 = adapter.to_pipeline_status(r["document_id"], "uploaded", None, None)
    check(ps4["status"] == "uploading", "uploaded -> uploading")


def test_defensive_empty():
    print("defensive: empty / missing input")
    for fn in (adapter.to_frontend_bill, adapter.to_frontend_flagset, adapter.to_frontend_appeal_score):
        out = fn({})
        check(isinstance(out, dict), "{} returns a dict on empty input".format(fn.__name__))
        out2 = fn(None)
        check(isinstance(out2, dict), "{} returns a dict on None input".format(fn.__name__))
    b = adapter.to_frontend_bill({})
    check(isinstance(b["lineItems"], list) and b["lineItems"] == [], "empty bill -> lineItems []")
    check(b["totals"]["reconciliation"]["ok"] is True, "empty bill -> reconciliation ok (no alarm)")
    check(b["extractionMode"] is None, "empty bill -> extractionMode None (no false 'live'/'sample' claim)")
    fs = adapter.to_frontend_flagset({})
    check(isinstance(fs["flags"], list) and fs["flags"] == [], "empty -> flags []")
    check(set(fs["summary"]["countByCategory"].keys()) == VALID_CATEGORIES, "empty -> all 10 category keys")
    ps = adapter.to_pipeline_status("x", "uploaded", None, None)
    check(ps["partialFlags"] is None, "empty pipeline -> partialFlags None (guarded parent)")


def main():
    for t in (test_bill, test_reconciliation_mismatch, test_flagset,
              test_appeal_score, test_pipeline_status, test_defensive_empty):
        t()
    print("\n{} checks run, {} failures".format(_checks, len(_failures)))
    if _failures:
        print("\nFAILURES:")
        for f in _failures:
            print("  - " + f)
        sys.exit(1)
    print("ALL PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
