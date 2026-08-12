use crate::types::{Flag, ParsedBill, Severity};

/// Rule ID for duplicate CPT detection.
const RULE_DUP_CPT: &str = "DUP-CPT-001";
/// Rule ID for duplicate CPT + same charge detection.
const RULE_DUP_CPT_CHARGE: &str = "DUP-CPT-CHARGE-002";

/// Detect duplicate line items.
///
/// Two levels of detection:
/// 1. Same CPT code appearing more than once → `duplicate` flag (high severity).
/// 2. Same CPT code AND near-identical charge amount → `duplicate` flag (critical severity),
///    since this strongly suggests a true billing duplicate.
pub fn detect_duplicates(bill: &mut ParsedBill) {
    let items = bill.line_items.clone();

    for (i, item_a) in items.iter().enumerate() {
        let Some(cpt_a) = item_a.cpt_hcpcs.as_deref() else {
            continue;
        };

        for (j, item_b) in items.iter().enumerate() {
            if i >= j {
                continue;
            }

            let Some(cpt_b) = item_b.cpt_hcpcs.as_deref() else {
                continue;
            };

            if cpt_a != cpt_b {
                continue;
            }

            // Same CPT code found — check if charges are also near-identical
            let charge_diff = (item_a.charge_amount - item_b.charge_amount).abs();
            let same_charge = charge_diff < 0.01;

            let (flag_type, severity, rule_id, message) = if same_charge {
                (
                    "duplicate",
                    Severity::Critical,
                    RULE_DUP_CPT_CHARGE,
                    format!(
                        "Possible duplicate charge: CPT {} appears more than once with identical charge ${:.2}.",
                        cpt_a, item_a.charge_amount
                    ),
                )
            } else {
                (
                    "duplicate",
                    Severity::High,
                    RULE_DUP_CPT,
                    format!(
                        "Possible duplicate charge: CPT {} appears more than once.",
                        cpt_a
                    ),
                )
            };

            let flag = Flag::new(flag_type, severity, message, rule_id);

            // Add flag to both items if not already present
            if let Some(line) = bill.line_items.get_mut(i) {
                if !line.flags.iter().any(|f| f.rule_id == Some(rule_id.to_string())) {
                    line.flags.push(flag.clone());
                }
            }
            if let Some(line) = bill.line_items.get_mut(j) {
                if !line.flags.iter().any(|f| f.rule_id == Some(rule_id.to_string())) {
                    line.flags.push(flag);
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{LineItem, Totals};

    fn make_item(id: &str, cpt: &str, charge: f64) -> LineItem {
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
        }
    }

    fn make_bill(items: Vec<LineItem>) -> ParsedBill {
        let billed: f64 = items.iter().map(|i| i.charge_amount).sum();
        ParsedBill {
            document_id: "test-doc".to_string(),
            status: "processing".to_string(),
            service_date: None,
            line_items: items,
            totals: Totals {
                billed,
                allowed: None,
                insurance_paid: None,
                patient_responsibility: None,
                potential_savings: None,
            },
        }
    }

    #[test]
    fn detects_duplicate_cpt() {
        let mut bill = make_bill(vec![
            make_item("1", "99285", 1000.0),
            make_item("2", "99285", 1200.0),
        ]);

        detect_duplicates(&mut bill);

        let dup_flags = bill.flags_of_type("duplicate");
        assert_eq!(dup_flags.len(), 2, "both items should be flagged");
        assert_eq!(dup_flags[0].rule_id.as_deref(), Some(RULE_DUP_CPT));
        assert_eq!(dup_flags[0].severity, "high");
    }

    #[test]
    fn detects_identical_charge_duplicate() {
        let mut bill = make_bill(vec![
            make_item("1", "93000", 275.0),
            make_item("2", "93000", 275.0),
        ]);

        detect_duplicates(&mut bill);

        let flags = bill.flags_of_type("duplicate");
        assert_eq!(flags.len(), 2);
        assert_eq!(flags[0].rule_id.as_deref(), Some(RULE_DUP_CPT_CHARGE));
        assert_eq!(flags[0].severity, "critical");
    }

    #[test]
    fn no_false_positive_for_different_cpts() {
        let mut bill = make_bill(vec![
            make_item("1", "99285", 1000.0),
            make_item("2", "80053", 150.0),
        ]);

        detect_duplicates(&mut bill);

        assert_eq!(bill.total_flags(), 0);
    }

    #[test]
    fn no_flag_when_cpt_missing() {
        let mut item = make_item("1", "99285", 1000.0);
        item.cpt_hcpcs = None;
        let mut bill = make_bill(vec![item, make_item("2", "99285", 1000.0)]);

        detect_duplicates(&mut bill);

        // Items without CPT codes cannot participate in duplicate detection,
        // and an item with a CPT can't match against an item without one.
        assert_eq!(bill.total_flags(), 0);
    }
}