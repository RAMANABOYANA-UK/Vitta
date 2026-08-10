use crate::rules::{duplicates, reconciliation, unbundling};
use crate::types::ParsedBill;

/// The main entry point for the rules engine.
///
/// Applies all rules to a `ParsedBill` and returns the enriched bill
/// with any detected flags attached to the relevant line items.
///
/// Rule execution order matters:
/// 1. **Reconciliation** first — catches math errors that may affect
///    the interpretation of other rules.
/// 2. **Duplicates** — identifies double-billed services.
/// 3. **Unbundling** — identifies component codes billed alongside
///    comprehensive codes (NCCI).
///
/// The function is pure and deterministic: given the same input, it
/// always produces the same output. This is critical for reproducible
/// audit trails and testing.
pub fn apply_rules(mut bill: ParsedBill) -> ParsedBill {
    // Order matters — run reconciliation first, then duplicates, then unbundling
    reconciliation::check_amount_reconciliation(&mut bill);
    duplicates::detect_duplicates(&mut bill);
    unbundling::detect_unbundling(&mut bill);

    bill
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{LineItem, Totals};

    fn make_item(
        id: &str,
        cpt: &str,
        charge: f64,
        allowed: Option<f64>,
        paid: Option<f64>,
        patient_resp: Option<f64>,
    ) -> LineItem {
        LineItem {
            id: id.to_string(),
            page: 1,
            description: format!("Service {}", cpt),
            cpt_hcpcs: Some(cpt.to_string()),
            icd10: vec![],
            units: 1.0,
            charge_amount: charge,
            allowed_amount: allowed,
            paid_amount: paid,
            patient_responsibility: patient_resp,
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
    fn apply_rules_runs_all_rule_modules() {
        // Duplicate CPT 93000 with identical charge
        // Sigmoidoscopy (45330) + Colonoscopy (45378) → unbundling
        // Correct math on all items
        let bill = make_bill(vec![
            make_item("1", "93000", 275.0, Some(95.0), Some(76.0), Some(19.0)),
            make_item("2", "93000", 275.0, Some(95.0), Some(76.0), Some(19.0)),
            make_item("3", "45330", 500.0, None, None, None),
            make_item("4", "45378", 2100.0, None, None, None),
            make_item("5", "80053", 150.0, Some(68.0), Some(54.4), Some(13.6)),
        ]);

        let result = apply_rules(bill);

        assert!(
            result.line_item_count() == 5,
            "bill should still have 5 items"
        );
        assert!(
            result.total_flags() >= 4,
            "expected at least 4 flags (2 duplicate + 2 unbundling), got {}",
            result.total_flags()
        );

        // Duplicate flags on items 1 & 2
        assert!(
            result.line_items[0]
                .flags
                .iter()
                .any(|f| f.rule_id.as_deref() == Some("DUP-CPT-CHARGE-002"))
        );
        // Unbundling flags on items 3 & 4
        assert!(
            result.line_items[2]
                .flags
                .iter()
                .any(|f| f.rule_id.as_deref() == Some("NCCI-UNBUNDLE-001"))
        );
    }

    #[test]
    fn clean_bill_has_no_flags() {
        let bill = make_bill(vec![
            make_item("1", "99285", 1000.0, None, None, None),
            make_item("2", "80053", 150.0, None, None, None),
        ]);

        let result = apply_rules(bill);

        assert_eq!(result.total_flags(), 0, "clean bill should have no flags");
    }

    #[test]
    fn engine_is_deterministic() {
        let build = || {
            make_bill(vec![
                make_item("1", "93000", 275.0, Some(95.0), Some(76.0), Some(19.0)),
                make_item("2", "93000", 275.0, Some(95.0), Some(76.0), Some(19.0)),
                make_item("3", "45330", 500.0, None, None, None),
                make_item("4", "45378", 2100.0, None, None, None),
            ])
        };

        let result_a = apply_rules(build());
        let result_b = apply_rules(build());

        let json_a = serde_json::to_string(&result_a).unwrap();
        let json_b = serde_json::to_string(&result_b).unwrap();

        assert_eq!(json_a, json_b, "rules engine must be deterministic");
    }
}