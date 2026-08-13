use crate::types::{Flag, LineItem, Totals};

/// Rule ID for line-item amount mismatch (allowed − paid ≠ patient resp).
const RULE_MATH_RECON: &str = "MATH-RECON-001";
/// Rule ID for paid exceeding allowed.
const RULE_PAID_EXCEEDS_ALLOWED: &str = "MATH-PAID-EXCEEDS-003";
/// Rule ID for totals mismatch (sum of line items ≠ stated total).
const RULE_TOTAL_MISMATCH: &str = "MATH-RECON-TOTALS-001";
/// Tolerance in dollars for float comparisons (5 cents).
const TOLERANCE_CENTS: f64 = 0.05;
/// Tolerance in dollars for totals reconciliation (billed vs sum of items).
const TOTALS_TOLERANCE: f64 = 1.0;

/// Check amount reconciliation on each line item.
///
/// For each item with allowed, paid, and patient responsibility amounts,
/// verify that `patient_responsibility ≈ max(allowed - paid, 0)`. Also
/// flags paid exceeding allowed (impossible in practice).
pub fn check_line_item_reconciliation(line_items: &mut [LineItem]) {
    for item in line_items.iter_mut() {
        let (Some(allowed), Some(paid), Some(patient_resp)) =
            (item.allowed_amount, item.paid_amount, item.patient_responsibility)
        else {
            continue;
        };

        let expected_patient = (allowed - paid).max(0.0);
        let difference = (patient_resp - expected_patient).abs();

        if difference > TOLERANCE_CENTS {
            item.flags.push(Flag {
                r#type: "math_error".to_string(),
                severity: "high".to_string(),
                message: format!(
                    "Amount mismatch: allowed (${:.2}) minus paid (${:.2}) should leave ~${:.2} patient responsibility, but the bill shows ${:.2}.",
                    allowed, paid, expected_patient, patient_resp
                ),
                rule_id: Some(RULE_MATH_RECON.to_string()),
                shap_contribution: None,
            });
        }

        if paid > allowed + TOLERANCE_CENTS {
            item.flags.push(Flag {
                r#type: "math_error".to_string(),
                severity: "critical".to_string(),
                message: format!(
                    "Paid amount ${:.2} exceeds allowed amount ${:.2} — insurance cannot pay more than the allowed amount.",
                    paid, allowed
                ),
                rule_id: Some(RULE_PAID_EXCEEDS_ALLOWED.to_string()),
                shap_contribution: None,
            });
        }
    }
}

/// Check that the sum of line-item charges roughly matches the billed total.
///
/// Returns `Some(Flag)` to be attached at the document level (the caller
/// decides where to attach it — currently the first line item, since the
/// Python `ParsedBill` schema has no separate document-level flags field).
pub fn check_totals_reconciliation(line_items: &[LineItem], totals: &Totals) -> Option<Flag> {
    let sum_charges: f64 = line_items.iter().map(|i| i.charge_amount).sum();
    let difference = (sum_charges - totals.billed).abs();

    if difference > TOTALS_TOLERANCE {
        Some(Flag {
            r#type: "math_error".to_string(),
            severity: "medium".to_string(),
            message: format!(
                "Line items sum to ${:.2}, but the bill's stated total is ${:.2} (difference ${:.2}).",
                sum_charges, totals.billed, difference
            ),
            rule_id: Some(RULE_TOTAL_MISMATCH.to_string()),
            shap_contribution: None,
        })
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
            service_date: None,
        }
    }

    #[test]
    fn flags_amount_mismatch() {
        // allowed 100, paid 80 → expected patient 20, but bill shows 30.
        let mut items = vec![make_item("1", "99285", 100.0, Some(100.0), Some(80.0), Some(30.0))];
        check_line_item_reconciliation(&mut items);
        assert_eq!(items[0].flags.len(), 1);
        let f = &items[0].flags[0];
        assert_eq!(f.rule_id.as_deref(), Some(RULE_MATH_RECON));
        assert_eq!(f.severity, "high");
        assert!(f.message.contains("$20.00"));
    }

    #[test]
    fn no_flag_when_math_is_correct() {
        let mut items = vec![make_item("1", "99285", 100.0, Some(100.0), Some(80.0), Some(20.0))];
        check_line_item_reconciliation(&mut items);
        assert!(items[0].flags.is_empty());
    }

    #[test]
    fn no_flag_when_amounts_missing() {
        let mut items = vec![make_item("1", "99285", 100.0, None, None, None)];
        check_line_item_reconciliation(&mut items);
        assert!(items[0].flags.is_empty());
    }

    #[test]
    fn flags_paid_exceeds_allowed() {
        let mut items = vec![make_item("1", "99285", 100.0, Some(100.0), Some(120.0), Some(0.0))];
        check_line_item_reconciliation(&mut items);
        assert_eq!(items[0].flags.len(), 1);
        let f = &items[0].flags[0];
        assert_eq!(f.rule_id.as_deref(), Some(RULE_PAID_EXCEEDS_ALLOWED));
        assert_eq!(f.severity, "critical");
    }

    #[test]
    fn flags_totals_mismatch() {
        let items = vec![
            make_item("1", "99285", 100.0, None, None, None),
            make_item("2", "80053", 50.0, None, None, None),
        ];
        let totals = Totals {
            billed: 175.0,
            ..Default::default()
        };
        let flag = check_totals_reconciliation(&items, &totals).expect("should flag");
        assert_eq!(flag.rule_id.as_deref(), Some(RULE_TOTAL_MISMATCH));
        assert!(flag.message.contains("$150.00"));
    }

    #[test]
    fn no_flag_when_totals_match() {
        let items = vec![make_item("1", "99285", 100.0, None, None, None)];
        let totals = Totals {
            billed: 100.0,
            ..Default::default()
        };
        assert!(check_totals_reconciliation(&items, &totals).is_none());
    }

    #[test]
    fn tolerates_cent_level_rounding() {
        // allowed 100, paid 89.99 → expected patient 10.01, bill shows 10.00
        // (0.01 diff < 0.05 tolerance → no flag).
        let mut items = vec![make_item("1", "99285", 100.0, Some(100.0), Some(89.99), Some(10.00))];
        check_line_item_reconciliation(&mut items);
        assert!(items[0].flags.is_empty());
    }
}