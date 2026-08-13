use crate::types::{Flag, LineItem};

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