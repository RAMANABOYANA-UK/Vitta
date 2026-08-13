//! # bill_rules
//!
//! Deterministic rules engine for medical bill analysis.
//!
//! The engine consumes a full `ParsedBill`-like JSON document, extracts
//! only the parts it needs (`line_items` + `totals`), runs deterministic
//! rules, and writes the enriched `line_items` back — **preserving every
//! other field exactly as received** (patient, provider, payer, letter,
//! audit, and any future fields the Python schema adds).
//!
//! Rules:
//! - **Amount reconciliation** — math errors in allowed/paid/patient responsibility
//! - **Duplicate detection** — same CPT + similar charge / same service date
//! - **NCCI unbundling** — component codes billed alongside comprehensive codes
//!
//! The engine is pure, deterministic, and easy to extend with new rules.

pub mod engine;
pub mod rules;
pub mod types;

use serde_json::Value;
use thiserror::Error;
use types::{RuleInput, RuleOutput, Totals};

/// Errors that can occur while applying rules to a JSON document.
#[derive(Debug, Error)]
pub enum EngineError {
    #[error("input document is not a JSON object")]
    NotAnObject,
    #[error("failed to parse line_items: {0}")]
    LineItemsParse(serde_json::Error),
    #[error("failed to parse totals: {0}")]
    TotalsParse(serde_json::Error),
    #[error("failed to serialize enriched line_items: {0}")]
    Serialize(serde_json::Error),
}

/// Apply the rules engine to a full `ParsedBill`-like JSON document.
///
/// # Opaque pass-through guarantee
///
/// This function only reads `line_items` and `totals` from the incoming
/// document, runs the rules, and writes the enriched `line_items` back.
/// Every other field — `patient`, `provider`, `payer`, `letter`, `audit`,
/// `denial_codes`, `appeal_prediction`, `explanation`, and any unknown
/// future fields — is left **completely untouched**.
///
/// # Robustness
///
/// - Missing `line_items` → treated as an empty array.
/// - Missing `totals` → treated as `Totals::default()` (billed = 0.0).
/// - Partial line items (missing optional fields) → parsed with serde
///   defaults rather than failing.
///
/// # Returns
///
/// The same JSON document with `line_items` replaced by the enriched
/// version. The `totals` field is preserved as-is (the engine never
/// mutates it).
pub fn apply_rules_to_document(mut doc: Value) -> Result<Value, EngineError> {
    let obj = doc.as_object_mut().ok_or(EngineError::NotAnObject)?;

    // Extract only the parts the engine needs.
    let line_items_value = obj
        .get("line_items")
        .cloned()
        .unwrap_or(Value::Array(vec![]));
    let totals_value = obj.get("totals").cloned().unwrap_or(Value::Null);

    let line_items =
        serde_json::from_value(line_items_value).map_err(EngineError::LineItemsParse)?;
    let totals: Totals = if totals_value.is_null() {
        Totals::default()
    } else {
        serde_json::from_value(totals_value).map_err(EngineError::TotalsParse)?
    };

    let input = RuleInput { line_items, totals };
    let output: RuleOutput = engine::apply_rules(input);

    // Write back ONLY the enriched line_items. Everything else in `obj`
    // (including `totals`) is preserved exactly as received.
    let enriched_line_items =
        serde_json::to_value(&output.line_items).map_err(EngineError::Serialize)?;
    obj.insert("line_items".to_string(), enriched_line_items);

    Ok(doc)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn preserves_unknown_fields_round_trip() {
        let doc = json!({
            "document_id": "doc-123",
            "status": "letter_ready",
            "patient": {"name": "Jane Doe", "member_id": "M123"},
            "provider": {"name": "Memorial Hospital", "npi": "1234567893"},
            "payer": {"name": "Acme Insurance", "claim_number": "GX-2025-883241"},
            "service_date": "2026-07-22",
            "line_items": [
                {
                    "id": "LI-1",
                    "description": "ER visit",
                    "cpt_hcpcs": "99284",
                    "charge_amount": 1240.0,
                    "allowed_amount": 800.0,
                    "paid_amount": 650.0,
                    "patient_responsibility": 150.0
                },
                {
                    "id": "LI-2",
                    "description": "ER visit (duplicate)",
                    "cpt_hcpcs": "99284",
                    "charge_amount": 1240.0,
                    "allowed_amount": 800.0,
                    "paid_amount": 650.0,
                    "patient_responsibility": 150.0
                }
            ],
            "totals": {"billed": 2480.0, "allowed": 1600.0, "insurance_paid": 1300.0, "patient_responsibility": 300.0},
            "denial_codes": [{"code": "CO-97", "reason": "bundled service"}],
            "appeal_prediction": {"success_probability": 0.72},
            "explanation": "The primary denial is CO-97.",
            "letter": {"status": "draft", "content_markdown": "# Appeal"},
            "audit": {"extraction_engine": "mock-v1", "pipeline_version": "0.1.0"},
            "future_unknown_field": {"nested": {"keep": "me"}}
        });

        let enriched = apply_rules_to_document(doc).expect("should succeed");

        // Unknown fields must be preserved byte-for-byte.
        assert_eq!(enriched["patient"]["name"], "Jane Doe");
        assert_eq!(enriched["provider"]["npi"], "1234567893");
        assert_eq!(enriched["payer"]["claim_number"], "GX-2025-883241");
        assert_eq!(enriched["service_date"], "2026-07-22");
        assert_eq!(enriched["denial_codes"][0]["code"], "CO-97");
        assert_eq!(enriched["appeal_prediction"]["success_probability"], 0.72);
        assert_eq!(enriched["explanation"], "The primary denial is CO-97.");
        assert_eq!(enriched["letter"]["status"], "draft");
        assert_eq!(enriched["audit"]["extraction_engine"], "mock-v1");
        assert_eq!(enriched["future_unknown_field"]["nested"]["keep"], "me");

        // Totals must be preserved exactly (engine never mutates them).
        assert_eq!(enriched["totals"]["billed"], 2480.0);
        assert_eq!(enriched["totals"]["allowed"], 1600.0);

        // Line items must be enriched with flags.
        let items = enriched["line_items"].as_array().unwrap();
        assert_eq!(items.len(), 2);
        let flags = items[0]["flags"].as_array().unwrap();
        assert!(!flags.is_empty(), "duplicate pair should be flagged");
        assert_eq!(flags[0]["rule_id"], "DUP-CPT-CHARGE-002");
    }

    #[test]
    fn handles_missing_line_items_and_totals() {
        let doc = json!({
            "document_id": "doc-456",
            "patient": {"name": "John Smith"}
        });

        let enriched = apply_rules_to_document(doc).expect("should succeed");
        assert_eq!(enriched["line_items"].as_array().unwrap().len(), 0);
        assert_eq!(enriched["patient"]["name"], "John Smith");
    }

    #[test]
    fn handles_partial_line_items() {
        let doc = json!({
            "document_id": "doc-789",
            "line_items": [
                {"id": "LI-1", "description": "ER visit", "charge_amount": 100.0}
            ],
            "totals": {"billed": 100.0}
        });

        let enriched = apply_rules_to_document(doc).expect("should succeed");
        let items = enriched["line_items"].as_array().unwrap();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0]["page"], 1, "missing page should default to 1");
        assert_eq!(items[0]["units"], 1.0, "missing units should default to 1.0");
        assert_eq!(items[0]["flags"].as_array().unwrap().len(), 0);
    }

    #[test]
    fn rejects_non_object_documents() {
        let err = apply_rules_to_document(json!([1, 2, 3])).unwrap_err();
        assert!(matches!(err, EngineError::NotAnObject));
    }

    #[test]
    fn rejects_invalid_line_items() {
        let doc = json!({
            "document_id": "doc-abc",
            "line_items": "not-an-array"
        });
        let err = apply_rules_to_document(doc).unwrap_err();
        assert!(matches!(err, EngineError::LineItemsParse(_)));
    }
}