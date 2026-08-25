"""
frontend_adapter.py — pure translation between the backend ParsedBill JSON
(as stored in ``Document.result_json``) and the frontend API contract defined
in ``js/api.js``.

WHY THIS EXISTS
    The frontend was built against a resource-oriented contract
    (``/bills/{id}``, ``/jobs/{id}/status``, ``FlagSet``, ``AppealScore``,
    ``PipelineStatus``) whose field names and shapes differ from the backend's
    ParsedBill. Rather than rewrite either side, the gateway router
    (``app/api/routes/gateway.py``) uses these functions to serve the
    frontend's exact shapes on top of the existing pipeline. Keeping the
    translation here — as pure ``dict -> dict`` functions with no
    FastAPI/SQLModel imports — means it can be unit-tested in isolation
    (see ``tests/test_frontend_adapter.py``) without a running database.

HONESTY DECISIONS (deliberate, not oversights)
    * ``evidence.codeReference`` is always ``None``. The backend does not
      attach a legal/policy citation to a flag, and fabricating one would
      pre-empt the citation-fabrication decision the team has explicitly
      deferred. ``source`` is described generically ("Deterministic rules
      engine" / "ML anomaly model" / "Payer denial (EOB)").
    * ``pages`` is always ``[]``. There is no OCR/page-image stage, so there
      are no page rasters to point at; the frontend renders an honest empty
      state ("Document pages will appear here after OCR.").
    * line-item ``verification`` is reported with ``method="absent"`` for
      every field, because nothing was OCR-verified. This surfaces the current
      capability gap rather than implying a confidence we do not have.
    * appeal-score ``factors`` is ``[]`` whenever the backend supplies only
      qualitative reason strings (its ``top_factors``); inventing a numeric
      per-factor ``impact`` would be fabrication. The reasons are preserved in
      ``basis`` instead. If a future model supplies *structured* factors
      (dicts carrying an ``impact``), they pass through unchanged.
    * appeal-score ``sampleSize`` is ``0`` unless the backend supplies a real
      count; the score is marked ``calibrated=false`` and ``basis`` explains it
      is a preliminary estimate. In mock-extraction mode the whole score is
      heuristic and the UI shows a degraded-mode banner (frontend workstream).

RECONCILIATION SEMANTICS
    The frontend shows a red "Reconciliation failed" banner whenever
    ``totals.reconciliation.ok`` is false, so ``ok`` is set false only on a
    genuine arithmetic inconsistency — specifically when the *allowed* amount
    does not equal *insurance paid + patient responsibility* (an invariant the
    pipeline data is expected to satisfy). The common, expected gap between
    *billed* and *allowed* (the insurer's contractual write-off) is NOT treated
    as a reconciliation failure. When the inputs are missing we report
    ``ok=true`` with an explanatory note rather than raising a false alarm.

All functions are defensive: they accept partial/empty/missing input and
always return a valid contract shape. They never raise on bad data.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Frontend enums / maps (kept in sync with js/api.js)
# ---------------------------------------------------------------------------

# The 10 flag categories the frontend understands. summary.countByCategory
# must contain every one of these keys.
_CATEGORIES: Tuple[str, ...] = (
    "duplicate_charge",
    "unbundling",
    "arithmetic_mismatch",
    "invalid_deprecated_code",
    "surprise_billing",
    "pricing_anomaly",
    "upcoding",
    "denied_claim",
    "missing_authorization",
    "coverage_gap",
)

# backend Flag.severity ("info"|"warning"|"critical") -> frontend ("low"|"medium"|"high")
_SEVERITY_MAP = {"info": "low", "warning": "medium", "critical": "high"}

# Keyword -> category. Checked in order against "<type> <message>" (lowercased).
# Specific patterns first; the generic pricing patterns come last so that a
# flag mentioning e.g. "coverage" is not swallowed by "price". Fallback is
# pricing_anomaly (the most generic "something is off with the amount").
_CATEGORY_RULES: Tuple[Tuple[str, str], ...] = (
    ("duplicate", "duplicate_charge"),
    ("unbundl", "unbundling"),
    ("bundl", "unbundling"),
    ("ncci", "unbundling"),
    ("arithmetic", "arithmetic_mismatch"),
    ("does not add", "arithmetic_mismatch"),
    ("doesn't add", "arithmetic_mismatch"),
    ("sum mismatch", "arithmetic_mismatch"),
    ("total mismatch", "arithmetic_mismatch"),
    ("deprecat", "invalid_deprecated_code"),
    ("retired", "invalid_deprecated_code"),
    ("invalid code", "invalid_deprecated_code"),
    ("code_mismatch", "invalid_deprecated_code"),
    ("code mismatch", "invalid_deprecated_code"),
    ("inconsistent with", "invalid_deprecated_code"),
    ("mismatch", "invalid_deprecated_code"),
    ("surprise", "surprise_billing"),
    ("out-of-network", "surprise_billing"),
    ("out of network", "surprise_billing"),
    ("balance bill", "surprise_billing"),
    ("no surprises", "surprise_billing"),
    ("upcod", "upcoding"),
    ("level of service", "upcoding"),
    ("higher level", "upcoding"),
    ("denial", "denied_claim"),
    ("denied", "denied_claim"),
    ("authoriz", "missing_authorization"),
    ("precert", "missing_authorization"),
    ("pre-cert", "missing_authorization"),
    ("prior auth", "missing_authorization"),
    ("not covered", "coverage_gap"),
    ("coverage", "coverage_gap"),
    ("benefit", "coverage_gap"),
    ("inflat", "pricing_anomaly"),
    ("overcharge", "pricing_anomaly"),
    ("percentile", "pricing_anomaly"),
    ("median", "pricing_anomaly"),
    ("pricing", "pricing_anomaly"),
    ("price", "pricing_anomaly"),
    ("anomaly", "pricing_anomaly"),
)

# Code shape detection. HCPCS is one letter + 4 digits (J1200, A0428, G0463);
# CPT is 5 digits (99284, 80053).
_HCPCS_RE = re.compile(r"^[A-Za-z]\d{4}$")
_CPT_RE = re.compile(r"^\d{5}$")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _round2(value: Any) -> Optional[float]:
    """Coerce to a 2dp float, or None if not numeric."""
    try:
        if value is None:
            return None
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _as_number(value: Any) -> Optional[float]:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _title_from_type(flag_type: Optional[str]) -> str:
    """'billing_code_mismatch' -> 'Billing Code Mismatch'."""
    if not flag_type:
        return "Billing issue"
    return str(flag_type).replace("_", " ").replace("-", " ").strip().title()


def _severity(sev: Any) -> str:
    return _SEVERITY_MAP.get(str(sev or "").lower(), "medium")


def _classify_category(flag_type: Optional[str], message: Optional[str]) -> str:
    hay = "{} {}".format(flag_type or "", message or "").lower()
    for keyword, category in _CATEGORY_RULES:
        if keyword in hay:
            return category
    return "pricing_anomaly"


def _code_fields(cpt_hcpcs: Optional[str]) -> Dict[str, Optional[str]]:
    """Split the backend's single ``cpt_hcpcs`` into the frontend's
    cptCode / hcpcsCode / code / codeType fields."""
    code = (cpt_hcpcs or "").strip()
    if not code:
        return {"cptCode": None, "hcpcsCode": None, "code": "", "codeType": None}
    if _HCPCS_RE.match(code):
        return {"cptCode": None, "hcpcsCode": code.upper(), "code": code.upper(), "codeType": "HCPCS"}
    if _CPT_RE.match(code):
        return {"cptCode": code, "hcpcsCode": None, "code": code, "codeType": "CPT"}
    # Unknown shape: still show it, but don't assert a type.
    return {"cptCode": None, "hcpcsCode": None, "code": code, "codeType": None}


def _absent_verification() -> Dict[str, Any]:
    """A FieldVerification stating, honestly, that nothing was OCR-verified."""
    return {
        "verified": False,
        "confidence": None,
        "method": "absent",
        "note": "No OCR verification available (extraction ran without OCR).",
    }


def _extraction_mode(extraction_path: Optional[str]) -> Optional[str]:
    """Map the backend audit ``extraction_path`` to the frontend's honesty mode.

    * ``"member2"`` -> ``"live"``: the real extraction service parsed the upload.
    * ``"mock"``    -> ``"sample"``: the pipeline synthesized fictional bill data
      seeded by the document id and did NOT read the user's file. The frontend
      shows a degraded-mode banner so no one mistakes sample figures for theirs.
    * anything else (incl. ``None``) -> ``None``: unknown; the frontend shows no
      claim either way.
    """
    if extraction_path == "member2":
        return "live"
    if extraction_path == "mock":
        return "sample"
    return None


def _line_items(result: Dict[str, Any], service_date: Optional[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for li in result.get("line_items") or []:
        if not isinstance(li, dict):
            continue
        codes = _code_fields(li.get("cpt_hcpcs"))
        icd = [
            {"code": str(c), "description": ""}
            for c in (li.get("icd10") or [])
            if c
        ]
        out.append(
            {
                "id": li.get("id") or "",
                "page": li.get("page") or 1,
                # No OCR -> no provenance box. Frontend guards `li.bbox ? ...`.
                "bbox": None,
                # Backend has a single bill-level service date; apply per line.
                "serviceDate": service_date,
                "cptCode": codes["cptCode"],
                "hcpcsCode": codes["hcpcsCode"],
                "code": codes["code"],
                "codeType": codes["codeType"],
                "description": li.get("description") or "",
                "units": _as_number(li.get("units")),
                "modifiers": list(li.get("modifiers") or []),
                # Not extracted by the backend; frontend guards this.
                "placeOfService": None,
                "icdCodes": icd,
                "amounts": {
                    "charge": _round2(li.get("charge_amount")),
                    "allowed": _round2(li.get("allowed_amount")),
                    "paid": _round2(li.get("paid_amount")),
                    "patientResponsibility": _round2(li.get("patient_responsibility")),
                },
                "verification": {
                    "amounts": _absent_verification(),
                    "description": _absent_verification(),
                    "code": _absent_verification(),
                    "date": _absent_verification(),
                },
            }
        )
    return out


def _reconciliation(line_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Check the per-line invariant: allowed == insurance_paid + patient_resp.

    Operates line-by-line rather than on totals on purpose. A fully-denied line
    legitimately has no ``allowed``/``paid`` but a full ``patient_responsibility``;
    at the *totals* level that makes ``allowed != paid + resp`` by exactly the
    denied amount, which would trip a false "Reconciliation failed" banner on
    most real bills. Denied / incomplete lines are therefore skipped here (they
    surface separately as denial flags), and ``ok`` is false only when a line
    that DOES carry all three amounts is internally inconsistent.
    """
    checked = 0
    max_diff = 0.0
    for li in line_items or []:
        if not isinstance(li, dict):
            continue
        amounts = li.get("amounts") or {}
        allowed = _as_number(amounts.get("allowed"))
        paid = _as_number(amounts.get("paid"))
        presp = _as_number(amounts.get("patientResponsibility"))
        if allowed is None or paid is None or presp is None:
            continue  # denied / not-yet-adjudicated line — not a reconciliation error
        checked += 1
        diff = abs(round(allowed - (paid + presp), 2))
        if diff > max_diff:
            max_diff = diff

    if checked == 0:
        return {
            "ok": True,
            "diff": None,
            "note": "No fully-adjudicated line items available to reconcile.",
        }
    if max_diff <= 0.01:
        return {
            "ok": True,
            "diff": 0.0,
            "note": "For every adjudicated line, the allowed amount equals insurance paid plus your responsibility.",
        }
    return {
        "ok": False,
        "diff": round(max_diff, 2),
        "note": (
            "At least one line item's allowed amount does not equal insurance paid "
            "plus your responsibility (largest gap ${:,.2f}). The amounts on this "
            "bill do not add up.".format(max_diff)
        ),
    }


# ---------------------------------------------------------------------------
# Flags — shared collection used by both the FlagSet and the flagged-amount total
# ---------------------------------------------------------------------------


def _shap_contribution(flag: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap the backend flag's single SHAP value + message as a why-contribution."""
    value = _as_number(flag.get("shap_contribution"))
    direction = "up" if (value is None or value >= 0) else "down"
    return {
        "feature": str(flag.get("type") or "model_signal"),
        "label": _title_from_type(flag.get("type")),
        "value": value,
        "direction": direction,
        "description": flag.get("message") or "",
    }


def _flag_from_line(
    line_id: str, charge: Optional[float], flag: Dict[str, Any], idx: int
) -> Dict[str, Any]:
    message = flag.get("message") or ""
    flag_type = flag.get("type")
    detection = "rule" if flag.get("rule_id") else "ml"
    return {
        "id": "{}::flag{}".format(line_id or "li", idx),
        "category": _classify_category(flag_type, message),
        "title": _title_from_type(flag_type),
        "severity": _severity(flag.get("severity")),
        # Backend has no calibrated per-flag confidence; the frontend defaults
        # null to 0.95 (rule) / 0.70 (ml) for display.
        "confidence": None,
        "detectionType": detection,
        "flagAmount": charge,
        "lineItemIds": [line_id] if line_id else [],
        "summary": message,
        "description": message,
        "why": {
            "title": "Why this was flagged",
            "contributions": [_shap_contribution(flag)],
        },
        "evidence": {
            # No fabricated citation (deferred decision). Source is generic.
            "codeReference": None,
            "source": "Deterministic rules engine" if detection == "rule" else "ML anomaly model",
        },
        "resolved": False,
    }


def _flag_from_denial(denial: Dict[str, Any], idx: int) -> Dict[str, Any]:
    code = str(denial.get("code") or "").upper()
    reason = denial.get("reason") or ""
    line_id = denial.get("line_item_id")
    return {
        "id": "denial::{}::{}".format(code or "code", idx),
        "category": "denied_claim",
        "title": "Claim denied — {}".format(code) if code else "Claim denied",
        "severity": _severity(denial.get("severity")),
        "confidence": None,
        # A payer denial is a stated fact from the EOB, not an ML inference.
        "detectionType": "rule",
        "flagAmount": _round2(denial.get("amount")),
        "lineItemIds": [line_id] if line_id else [],
        "summary": reason,
        "description": reason,
        "why": {
            "title": "Why this was flagged",
            "contributions": [
                {
                    "feature": "denial_code",
                    "label": "Payer denial code",
                    "value": None,
                    "direction": "up",
                    "description": "{}: {}".format(code, reason) if code else reason,
                }
            ],
        },
        "evidence": {"codeReference": None, "source": "Payer denial (EOB)"},
        "resolved": False,
    }


def _collect_flags(result: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """Build the full frontend flag list (line-item anomalies + payer denials)
    and a map of line-item id -> charge (used for the flagged-amount total)."""
    charge_map: Dict[str, float] = {}
    for li in result.get("line_items") or []:
        if isinstance(li, dict) and li.get("id") is not None:
            charge = _round2(li.get("charge_amount"))
            if charge is not None:
                charge_map[str(li["id"])] = charge

    flags: List[Dict[str, Any]] = []
    for li in result.get("line_items") or []:
        if not isinstance(li, dict):
            continue
        line_id = str(li.get("id") or "")
        charge = charge_map.get(line_id)
        for i, flag in enumerate(li.get("flags") or [], start=1):
            if isinstance(flag, dict):
                flags.append(_flag_from_line(line_id, charge, flag, i))

    for i, denial in enumerate(result.get("denial_codes") or [], start=1):
        if isinstance(denial, dict):
            flags.append(_flag_from_denial(denial, i))

    return flags, charge_map


def _total_flagged_amount(flags: List[Dict[str, Any]], charge_map: Dict[str, float]) -> float:
    """Sum the charge of each DISTINCT flagged line item (deduped so a line
    carrying several flags is not counted multiple times). Flags with no
    resolvable line item fall back to their own flagAmount."""
    flagged_ids = set()
    orphan_total = 0.0
    for f in flags:
        ids = [i for i in (f.get("lineItemIds") or []) if i in charge_map]
        if ids:
            flagged_ids.update(ids)
        else:
            amt = _as_number(f.get("flagAmount"))
            if amt is not None:
                orphan_total += amt
    known_total = sum(charge_map[i] for i in flagged_ids)
    return round(known_total + orphan_total, 2)


# ---------------------------------------------------------------------------
# Public translators
# ---------------------------------------------------------------------------


def to_frontend_bill(result: Optional[Dict[str, Any]], document_id: Optional[str] = None) -> Dict[str, Any]:
    """Translate a backend ParsedBill dict into the frontend ``ParsedBill`` shape."""
    result = result or {}
    doc_id = document_id or result.get("document_id") or ""
    provider = result.get("provider") or {}
    payer = result.get("payer") or {}
    patient = result.get("patient") or {}
    totals = result.get("totals") or {}
    service_date = result.get("service_date")

    line_items = _line_items(result, service_date)

    # Extraction mode drives the frontend's honesty banner. In "mock" mode the
    # pipeline did NOT read the user's upload — it synthesized fictional bill
    # data seeded by the document id (see data-extraction mock_data.py) — so the
    # UI must warn that the figures below are sample data, not their real bill.
    extraction_mode = _extraction_mode((result.get("audit") or {}).get("extraction_path"))
    extraction_warnings = result.get("extraction_warnings") or result.get("extractionWarnings") or []
    # Honest record of how the document text was produced ("pdf_text" | "ocr" |
    # "none"), when the pipeline recorded it. Lets clients distinguish a real
    # PDF read from sample data without over-claiming structured extraction.
    text_extraction_method = (
        ((result.get("audit") or {}).get("text_extraction") or {}).get("method") or None
    )

    bill: Dict[str, Any] = {
        "documentId": doc_id,
        # Backend has no separate job concept — job id mirrors the document id.
        "jobId": doc_id,
        "metadata": {
            "provider": provider.get("name"),
            "providerNpi": provider.get("npi"),
            "payer": payer.get("name"),
            # Overview labels this "service date"; backend has a real one.
            "statementDate": service_date,
            # Overview labels this "claim"; surface the real claim number.
            "accountRef": payer.get("claim_number"),
            "memberName": patient.get("name"),
            "memberId": patient.get("member_id"),
            "patientLiability": _round2(totals.get("patient_responsibility")),
        },
        "totals": {
            "billed": _round2(totals.get("billed")),
            "allowed": _round2(totals.get("allowed")),
            # NOTE the rename: backend `insurance_paid` -> frontend `paid`.
            "paid": _round2(totals.get("insurance_paid")),
            "patientResponsibility": _round2(totals.get("patient_responsibility")),
            "reconciliation": _reconciliation(line_items),
        },
        "lineItems": line_items,
        # No OCR stage -> no page rasters. Frontend shows an honest empty state.
        "pages": [],
        "extractionWarnings": extraction_warnings,
        "extractionStatus": "complete" if line_items else "partial",
        # "sample" | "live" | None. Frontend shows a degraded-mode banner when
        # this is "sample" (data was synthesized, not read from the upload).
        "extractionMode": extraction_mode,
        # How the raw document text was produced, or None if not recorded.
        "textExtractionMethod": text_extraction_method,
    }

    # Harmless extra field (frontend ignores unknown keys): the verified appeal
    # letter, so app.js can prefer it over its client-side template.
    letter = result.get("letter")
    if isinstance(letter, dict):
        bill["letter"] = {
            "status": letter.get("status"),
            "contentMarkdown": letter.get("content_markdown"),
            "verifiedFields": list(letter.get("verified_fields") or []),
            "verificationPassed": bool(letter.get("verification_passed")),
            "problems": list(letter.get("problems") or []),
        }
    else:
        bill["letter"] = None

    return bill


def to_frontend_flagset(result: Optional[Dict[str, Any]], document_id: Optional[str] = None) -> Dict[str, Any]:
    """Translate backend line-item flags + denials into the frontend ``FlagSet``."""
    result = result or {}
    doc_id = document_id or result.get("document_id") or ""

    flags, charge_map = _collect_flags(result)

    count_by_category = {cat: 0 for cat in _CATEGORIES}
    rule_count = 0
    ml_count = 0
    for f in flags:
        cat = f.get("category")
        if cat in count_by_category:
            count_by_category[cat] += 1
        if f.get("detectionType") == "rule":
            rule_count += 1
        else:
            ml_count += 1

    return {
        "documentId": doc_id,
        "flags": flags,
        "complete": True,
        "summary": {
            "totalFlaggedAmount": _total_flagged_amount(flags, charge_map),
            "countByCategory": count_by_category,
            "ruleCount": rule_count,
            "mlCount": ml_count,
        },
    }


def _build_basis(explanation: Optional[str], reasons: List[str]) -> str:
    parts: List[str] = []
    if explanation:
        parts.append(str(explanation).strip())
    if reasons:
        parts.append("Key factors considered: " + "; ".join(r.strip() for r in reasons if r.strip()) + ".")
    if not parts:
        return "Preliminary estimate based on the detected billing issues."
    return " ".join(parts)


def _passthrough_factor(f: Dict[str, Any]) -> Dict[str, Any]:
    impact = _as_number(f.get("impact")) or 0.0
    direction = f.get("direction") or ("up" if impact >= 0 else "down")
    return {
        "key": str(f.get("key") or f.get("feature") or "factor"),
        "label": f.get("label") or _title_from_type(f.get("key") or f.get("feature")),
        "impact": impact,
        "direction": direction,
        "description": f.get("description") or "",
        "actionable": bool(f.get("actionable", False)),
    }


def to_frontend_appeal_score(result: Optional[Dict[str, Any]], document_id: Optional[str] = None) -> Dict[str, Any]:
    """Translate the backend ``appeal_prediction`` into the frontend ``AppealScore``.

    See the module docstring for why factors may be folded into ``basis`` and
    why ``sampleSize`` defaults to 0 / ``calibrated`` is false.
    """
    result = result or {}
    doc_id = document_id or result.get("document_id") or ""
    ap = result.get("appeal_prediction")
    audit = result.get("audit") or {}
    updated_at = audit.get("completed_at")

    if not isinstance(ap, dict):
        return {
            "documentId": doc_id,
            "score": None,
            "calibrated": False,
            "modelVersion": None,
            "confidenceInterval": None,
            "sampleSize": 0,
            "calibration": None,
            "basis": "Appeal score is not available for this document.",
            "factors": [],
            "updatedAt": updated_at,
            "stale": False,
        }

    ci = ap.get("confidence_interval")
    if isinstance(ci, (list, tuple)) and len(ci) == 2 and all(_as_number(x) is not None for x in ci):
        confidence_interval = [_round2(ci[0]), _round2(ci[1])]
    else:
        confidence_interval = None

    top_factors = ap.get("top_factors") or []
    structured = [f for f in top_factors if isinstance(f, dict) and "impact" in f]
    if structured:
        factors = [_passthrough_factor(f) for f in structured]
        basis = str(result.get("explanation") or "").strip() or "Model-derived appeal factors."
    else:
        # Only qualitative strings available — fold them into basis rather than
        # inventing numeric impacts.
        factors = []
        reasons = [str(f) for f in top_factors if isinstance(f, str) and str(f).strip()]
        basis = _build_basis(result.get("explanation"), reasons)

    # A real corpus size may arrive on the prediction later; until then, 0.
    sample_size = _as_number(ap.get("sample_size"))
    sample_size = int(sample_size) if sample_size is not None else 0

    return {
        "documentId": doc_id,
        "score": _round2(ap.get("success_probability")),
        # Heuristic/uncalibrated until a calibrated model is wired in.
        "calibrated": False,
        "modelVersion": ap.get("model_version"),
        "confidenceInterval": confidence_interval,
        "sampleSize": sample_size,
        "calibration": None,
        "basis": basis,
        "factors": factors,
        "updatedAt": updated_at,
        "stale": False,
    }


# ---------------------------------------------------------------------------
# Pipeline status
# ---------------------------------------------------------------------------

# Backend DocumentStatus -> (frontend status, progress). The backend pipeline
# is coarse (uploaded -> processing -> analyzed -> letter_ready / error); it has
# no OCR sub-stages, so we pick a representative frontend status per state.
_STATUS_MAP = {
    "uploaded": ("uploading", 5),
    "processing": ("extraction_running", 45),
    "analyzed": ("ml_scoring_running", 80),
    "letter_ready": ("done", 100),
    "error": ("failed", 100),
}


def _stages(backend_status: str, extraction_path: Optional[str], error_message: Optional[str]) -> List[Dict[str, Any]]:
    """Synthesize a frontend stage list from the coarse backend status.

    OCR/preprocessing are marked "skipped" when running on mock extraction
    (there is genuinely no OCR), and "done" when the real extraction service
    (which performs OCR upstream) is enabled. This is honest about what ran.
    """
    ocr_state = "done" if _extraction_mode(extraction_path) == "live" else "skipped"

    # Order matters — mirrors the frontend STAGE_SEQUENCE names.
    names = ["preprocessing", "ocr_running", "extraction_running", "validation_running", "ml_scoring_running"]

    # How far the pipeline has progressed, by backend status.
    done_through = {
        "uploaded": -1,
        "processing": 1,        # OCR resolved; extraction is the active work
        "analyzed": 3,          # extraction + validation done; ml is active
        "letter_ready": 4,      # everything done
        "error": None,          # a stage failed
    }.get(backend_status, -1)

    stages: List[Dict[str, Any]] = []
    for idx, name in enumerate(names):
        base = {"name": name, "startedAt": None, "completedAt": None, "error": None, "errorCode": None}
        if name in ("preprocessing", "ocr_running") and ocr_state == "skipped":
            base["status"] = "skipped"
            stages.append(base)
            continue

        if backend_status == "error":
            # We don't know which sub-stage failed; mark the pipeline's active
            # analytic stage as failed and leave the rest pending.
            if name == "extraction_running":
                base["status"] = "failed"
                base["error"] = error_message or "Processing failed"
                base["errorCode"] = "PIPELINE_ERROR"
            else:
                base["status"] = "pending"
            stages.append(base)
            continue

        if done_through is None:
            base["status"] = "pending"
        elif idx <= done_through:
            base["status"] = "done"
        elif idx == done_through + 1:
            base["status"] = "running"
        else:
            base["status"] = "pending"
        stages.append(base)

    return stages


def to_pipeline_status(
    document_id: str,
    backend_status: str,
    error_message: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Translate a Document's coarse status (+ stored result, if any) into the
    frontend ``PipelineStatus``. When a result is present, the parsed bill,
    flags, and appeal score are embedded as ``partialBill`` / ``partialFlags`` /
    ``partialScore`` so the frontend can render everything from one status poll
    (its ``getFlags`` / ``getAppealScore`` are otherwise never called)."""
    status_value, progress = _STATUS_MAP.get(backend_status, ("uploading", 5))
    audit = (result or {}).get("audit") or {}
    extraction_path = audit.get("extraction_path")

    failure = None
    if status_value == "failed":
        failure = {"code": "PIPELINE_ERROR", "message": error_message or "Processing failed."}

    has_result = isinstance(result, dict) and bool(result)
    partial_bill = to_frontend_bill(result, document_id) if has_result else None
    partial_flags = to_frontend_flagset(result, document_id) if has_result else None
    partial_score = to_frontend_appeal_score(result, document_id) if has_result else None
    extraction_warnings = (result or {}).get("extraction_warnings") or (result or {}).get("extractionWarnings") or []

    return {
        "jobId": document_id,
        "documentId": document_id,
        "status": status_value,
        "progress": progress,
        "stages": _stages(backend_status, extraction_path, error_message),
        "failure": failure,
        "partial": has_result,
        "partialBill": partial_bill,
        "partialFlags": partial_flags,
        "partialScore": partial_score,
        "extractionWarnings": extraction_warnings,
    }
