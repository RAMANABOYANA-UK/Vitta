You are a senior backend + systems engineer working on the Vitta medical bill intelligence platform (Member 3 role).

I own:
- `medical-bill-backend` (FastAPI)
- `bill_rules` (Rust deterministic rules engine)

A code review found several real issues. Fix all of them cleanly and production-oriented.

### Issues to Fix

**Rust Rules Engine (`bill_rules`)**
1. Uses opaque `serde_json::Value` in a fragile way.
2. Only updates `line_items` and does not handle the document robustly.
3. Must preserve all unknown fields so Member 2’s extra fields survive the round-trip.
4. NCCI unbundling pairs are too few / some are weak.
5. Error handling and logging need to be clearer.
6. Health endpoint and service robustness should be improved.

**Python Backend (`medical-bill-backend`)**
1. Background task (`_process_document_background`) is fragile — status can get stuck in `processing` even when the pipeline succeeded.
2. Status transitions and error handling in the background task are incomplete.
3. `PATCH /documents/{id}/letter` accepts a raw `dict` instead of a proper Pydantic model.
4. Health endpoint does not check whether the Rust rules service is reachable.
5. Status strings are sometimes hardcoded instead of using the `DocumentStatus` enum consistently.
6. Letter verifier only checks 5-digit CPT codes (misses HCPCS) and can be strengthened.
7. Overall: make the pipeline more reliable with graceful degradation.

### Required Outcomes

**Rust side**
- Harden `apply_rules_to_document` so it:
  - Safely extracts only what it needs (`line_items` + `totals`)
  - Runs duplicates, reconciliation, and unbundling rules
  - Writes enriched `line_items` back
  - Preserves every other field in the JSON exactly
- Improve rule quality and messages
- Expand NCCI starter pairs with more realistic common pairs
- Keep the HTTP API stable: `GET /health` and `POST /apply-rules` on port 3001
- Better structured logging (document_id, flags added, errors)

**Python side**
- Make the background pipeline task reliable:
  - Always persist `result_json` when the pipeline succeeds
  - Always move to a terminal status (`letter_ready` or `error`)
  - Never leave a document stuck in `processing`
- Add a proper Pydantic request model for letter editing
- Improve `GET /health` so it reports rules-engine reachability
- Strengthen `letter_verifier.py` (support HCPCS-style codes, cleaner checks)
- Use `DocumentStatus` enum consistently
- Keep graceful fallback when Rust service or LLM is unavailable

### Deliverables
Provide complete, ready-to-paste updated code for:

**Rust**
- `bill_rules/src/lib.rs`
- `bill_rules/src/main.rs`
- `bill_rules/src/types.rs` (if changed)
- `bill_rules/src/engine.rs`
- `bill_rules/src/rules/*.rs`
- Any needed `Cargo.toml` changes

**Python**
- `app/api/routes/documents.py` (background task + letter endpoint)
- `app/api/routes/health.py`
- `app/services/letter_verifier.py`
- `app/services/pipeline.py` (if needed)
- `app/schemas.py` (add letter update model if needed)
- Any small config improvements

Also give a short summary of every fix you made and how to verify them.

### Principles
- Deterministic rules stay in Rust
- Never let hallucinated data reach the user
- Preserve unknown fields across the Rust boundary
- Graceful degradation everywhere
- Clean, typed, production-quality code
- Do not break the existing Python ↔ Rust contract

Start implementing all fixes now.use crate::types::{Flag, LineItem};

/// Rule ID for same-CPT + same-date duplicate detection.
const RULE_DUP_CPT_SAME_DATE: &str = "DUP-CPT-001";
/// Rule ID for same-CPT + near-identical charge duplicate detection.
const RULE_DUP_CPT_CHARGE: &str = "DUP-CPT-CHARGE-002";
/// Charge tolerance in dollars — two charges within $0.01 are "identical."
const CHARGE_TOLERANCE: f64 = 0.01;

/// Detect likely duplicate line items.
///
/// Three levels of detection, each producing a distinct severity:
/// 1. Same CPT code AND near-identical charge amount → `high` (strong
///    evidence of a true billing duplicate).
/// 2. Same CPT code AND same service date (when both are present) → `high`
///    (double-billed on the same day).
/// 3. Same CPT code with no date comparison possible → `medium` (possible
///    duplicate; dates couldn't be confirmed as different).
///
/// Flags are added to **both** items involved in the match, deduplicated
/// by `rule_id` + `message` so repeated pair scans never stack duplicates.
pub fn detect_duplicates(line_items: &mut [LineItem]) {
    // Snapshot the fields we compare against before mutating flags.
    let snapshot: Vec<(usize, Option<String>, Option<String>, f64)> = line_items
        .iter()
        .enumerate()
        .map(|(i, item)| {
            (
                i,
                item.cpt_hcpcs.clone(),
                item.service_date.clone(),
                item.charge_amount,
            )
        })
        .collect();

    for a in 0..snapshot.len() {
        for b in (a + 1)..snapshot.len() {
            let (idx_a, cpt_a, date_a, charge_a) = &snapshot[a];
            let (idx_b, cpt_b, date_b, charge_b) = &snapshot[b];

            let (Some(cpt_a), Some(cpt_b)) = (cpt_a, cpt_b) else { continue };
            if cpt_a != cpt_b {
                continue;
            }

            let same_charge = (charge_a - charge_b).abs() <= CHARGE_TOLERANCE;
            let same_date = match (date_a, date_b) {
                (Some(d1), Some(d2)) => Some(d1 == d2),
                _ => None,
            };

            // Determine which flag (if any) applies to this pair.
            let (rule_id, severity, message) = if same_charge {
                (
                    RULE_DUP_CPT_CHARGE,
                    "high",
                    format!(
                        "Likely duplicate: CPT {} billed twice with the same charge ${:.2}.",
                        cpt_a, charge_a
                    ),
                )
            } else {
                match same_date {
                    Some(true) => (
                        RULE_DUP_CPT_SAME_DATE,
                        "high",
                        format!(
                            "Likely duplicate: CPT {} billed twice on the same date of service.",
                            cpt_a
                        ),
                    ),
                    Some(false) => continue, // same CPT but confirmed different dates — not a duplicate
                    None => (
                        RULE_DUP_CPT_SAME_DATE,
                        "medium",
                        format!(
                            "Possible duplicate: CPT {} appears more than once (dates could not be confirmed as different).",
                            cpt_a
                        ),
                    ),
                }
            };

            let flag = Flag {
                r#type: "duplicate".to_string(),
                severity: severity.to_string(),
                message,
                rule_id: Some(rule_id.to_string()),
                shap_contribution: None,
            };

            // Add the flag to both items, skipping if already present.
            for idx in [*idx_a, *idx_b] {
                if !line_items[idx]
                    .flags
                    .iter()
                    .any(|f| f.rule_id == flag.rule_id && f.message == flag.message)
                {
                    line_items[idx].flags.push(flag.clone());
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_item(id: &str, cpt: &str, charge: f64, date: Option<&str>) -> LineItem {
        LineItem {
            id: id.to_string(),
            page: 1,
            description: format!("Service {}", cpt),
            cpt_hcpcs: Some(cpt.to_string()),
            icd10: vec![],
            units: 1.0,
            charge_amount: charge,
            allowed_amount: None,
            paid_amount: None,
            patient_responsibility: None,
            modifiers: vec![],
            flags: vec![],
            service_date: date.map(|s| s.to_string()),
        }
    }

    #[test]
    fn detects_same_charge_duplicate() {
        let mut items = vec![
            make_item("1", "93000", 275.0, None),
            make_item("2", "93000", 275.0, None),
        ];
        detect_duplicates(&mut items);
        assert_eq!(items[0].flags.len(), 1);
        assert_eq!(items[1].flags.len(), 1);
        let flag = &items[0].flags[0];
        assert_eq!(flag.severity, "high");
        assert_eq!(flag.rule_id.as_deref(), Some(RULE_DUP_CPT_CHARGE));
        assert!(flag.message.contains("same charge"));
    }

    #[test]
    fn detects_same_date_duplicate() {
        let mut items = vec![
            make_item("1", "99285", 1000.0, Some("2026-07-22")),
            make_item("2", "99285", 1200.0, Some("2026-07-22")),
        ];
        detect_duplicates(&mut items);
        assert_eq!(items[0].flags.len(), 1);
        let flag = &items[0].flags[0];
        assert_eq!(flag.severity, "high");
        assert_eq!(flag.rule_id.as_deref(), Some(RULE_DUP_CPT_SAME_DATE));
        assert!(flag.message.contains("same date"));
    }

    #[test]
    fn no_flag_when_cpt_differs() {
        let mut items = vec![
            make_item("1", "99285", 1000.0, None),
            make_item("2", "80053", 150.0, None),
        ];
        detect_duplicates(&mut items);
        assert!(items[0].flags.is_empty());
        assert!(items[1].flags.is_empty());
    }

    #[test]
    fn no_flag_when_same_cpt_different_dates() {
        let mut items = vec![
            make_item("1", "99285", 1000.0, Some("2026-07-22")),
            make_item("2", "99285", 700.0, Some("2026-08-01")),
        ];
        detect_duplicates(&mut items);
        assert!(items[0].flags.is_empty());
        assert!(items[1].flags.is_empty());
    }

    #[test]
    fn flags_are_deduplicated() {
        // Three identical items — each pair generates the same flag;
        // ensure no item ends up with duplicate flags stacked.
        let mut items = vec![
            make_item("1", "93000", 275.0, None),
            make_item("2", "93000", 275.0, None),
            make_item("3", "93000", 275.0, None),
        ];
        detect_duplicates(&mut items);
        for item in items.iter() {
            assert_eq!(item.flags.len(), 1, "item {} should have exactly 1 flag", item.id);
        }
    }
}