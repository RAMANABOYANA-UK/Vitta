use crate::types::{Flag, ParsedBill, Severity};

/// Rule ID for line-item math reconciliation errors.
const RULE_MATH_RECON: &str = "MATH-RECON-001";
/// Rule ID for totals mismatch.
const RULE_TOTAL_MISMATCH: &str = "TOTAL-RECON-002";
/// Tolerance in dollars for float comparisons (5 cents).
const MONEY_TOLERANCE: f64 = 0.05;

/// Check amount reconciliation on each line item.
///
/// For each item with allowed, paid, and patient responsibility amounts,
/// verify that: `patient_responsibility ≈ allowed - paid` (non-negative).
///
/// Also checks that the sum of line-item charges matches the billed total.
pub fn check_amount_reconciliation(bill: &mut ParsedBill) {
    for item in bill.line_items.iter_mut() {
        if let (Some(allowed), Some(paid), Some(patient_resp)) = (
            item.allowed_amount,
            item.paid_amount,
            item.patient_responsibility,
        ) {
            let expected_patient = (allowed - paid).max(0.0);
            let difference = (patient_resp - expected_patient).abs();

            if difference > MONEY_TOLERANCE {
                item.flags.push(Flag::new(
                    "math_error",
                    Severity::High,
                    format!(
                        "Amount mismatch: Expected patient responsibility ≈ ${:.2}, found ${:.2} (difference ${:.2})",
                        expected_patient, patient_resp, difference
                    ),
                    RULE_MATH_RECON,
                ));
            }

            // Paid should never exceed allowed (insurance can't pay more than allowed)
            if paid > allowed + MONEY_TOLERANCE {
                item.flags.push(Flag::new(
                    "math_error",
                    Severity::Critical,
                    format!(
                        "Paid amount ${:.2} exceeds allowed amount ${:.2}",
                        paid, allowed
                    ),
                    "MATH-PAID-EXCEEDS-003",
                ));
            }
        }

        // Paid amount without allowed amount is suspicious
        if item.paid_amount.is_some() && item.allowed_amount.is_none() {
            item.flags.push(Flag::new(
                "data_quality",
                Severity::Warning,
                "Paid amount present but allowed amount missing.",
                "DQ-PAID-NO-ALLOWED-004",
            ));
        }
    }

    check_totals(bill);
}

/// Verify the sum of line-item charges approximately matches the billed total.
fn check_totals(bill: &mut ParsedBill) {
    let sum_charges: f64 = bill.line_items.iter().map(|i| i.charge_amount).sum();
    let difference = (sum_charges - bill.totals.billed).abs();

    if difference > 1.0 {
        // Bill-level flag — attach to the first line item so the Python backend
        // can find it easily. In a future iteration we'll add document-level flags.
        if let Some(first) = bill.line_items.first_mut() {
            first.flags.push(Flag::new(
                "math_error",
                Severity::Critical,
                format!(
                    "Totals mismatch: sum of line items ${:.2} != billed total ${:.2} (difference ${:.2})",
                    sum_charges, bill.totals.billed, difference
                ),
                RULE_TOTAL_MISMATCH,
            ));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{LineItem, Totals};

    fn make_item(
        id: &str,
        charge: f64,
        allowed: Option<f64>,
        paid: Option<f64>,
        patient_resp: Option<f64>,
    ) -> LineItem {
        LineItem {
            id: id.to_string(),
            page: 1,
            description: "Test service".to_string(),
            cpt_hcpcs: Some("99285".to_string()),
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

    #[test]
    fn flags_math_error_when_patient_resp_is_wrong() {
        // allowed=100, paid=80 → expected patient_resp = 20
        let mut bill = ParsedBill {
            document_id: "test".to_string(),
            status: "processing".to_string(),
            service_date: None,
            line_items: vec![make_item("1", 100.0, Some(100.0), Some(80.0), Some(30.0))],
            totals: Totals {
                billed: 100.0,
                allowed: Some(100.0),
                insurance_paid: Some(80.0),
                patient_responsibility: Some(30.0),
                potential_savings: None,
            },
        };

        check_amount_reconciliation(&mut bill);

        let math_flags = bill.flags_of_type("math_error");
        assert!(
            !math_flags.is_empty(),
            "expected math_error flag for incorrect patient responsibility"
        );
        assert_eq!(math_flags[0].rule_id.as_deref(), Some(RULE_MATH_RECON));
    }

    #[test]
    fn no_flag_when_math_is_correct() {
        let mut bill = ParsedBill {
            document_id: "test".to_string(),
            status: "processing".to_string(),
            service_date: None,
            line_items: vec![make_item("1", 100.0, Some(100.0), Some(80.0), Some(20.0))],
            totals: Totals {
                billed: 100.0,
                allowed: Some(100.0),
                insurance_paid: Some(80.0),
                patient_responsibility: Some(20.0),
                potential_savings: None,
            },
        };

        check_amount_reconciliation(&mut bill);

        assert_eq!(bill.total_flags(), 0, "no flags expected for correct math");
    }

    #[test]
    fn flags_when_paid_exceeds_allowed() {
        // paid=120 > allowed=100 — impossible in practice
        let mut bill = ParsedBill {
            document_id: "test".to_string(),
            status: "processing".to_string(),
            service_date: None,
            line_items: vec![make_item("1", 100.0, Some(100.0), Some(120.0), Some(0.0))],
            totals: Totals {
                billed: 100.0,
                allowed: Some(100.0),
                insurance_paid: Some(120.0),
                patient_responsibility: Some(0.0),
                potential_savings: None,
            },
        };

        check_amount_reconciliation(&mut bill);

        assert_eq!(bill.total_flags(), 1, "expected one math_error flag");
        assert!(
            bill.flags_of_type("math_error")[0]
                .message
                .contains("exceeds allowed"),
            "message should mention paid exceeds allowed"
        );
    }

    #[test]
    fn flags_totals_mismatch() {
        // Line items sum to 150, but totals.billed = 175
        let mut bill = ParsedBill {
            document_id: "test".to_string(),
            status: "processing".to_string(),
            service_date: None,
            line_items: vec![
                make_item("1", 100.0, None, None, None),
                make_item("2", 50.0, None, None, None),
            ],
            totals: Totals {
                billed: 175.0,
                allowed: None,
                insurance_paid: None,
                patient_responsibility: None,
                potential_savings: None,
            },
        };

        check_amount_reconciliation(&mut bill);

        assert_eq!(bill.total_flags(), 1);
        assert_eq!(
            bill.flags_of_type("math_error")[0].rule_id.as_deref(),
            Some(RULE_TOTAL_MISMATCH)
        );
    }

    #[test]
    fn tolerates_cent_level_rounding() {
        // 100.00 - 89.99 = 10.01 but patient_resp = 10.00 (rounding diff < 5c)
        let mut bill = ParsedBill {
            document_id: "test".to_string(),
            status: "processing".to_string(),
            service_date: None,
            line_items: vec![make_item("1", 100.0, Some(100.0), Some(89.99), Some(10.00))],
            totals: Totals {
                billed: 100.0,
                allowed: Some(100.0),
                insurance_paid: Some(89.99),
                patient_responsibility: Some(10.00),
                potential_savings: None,
            },
        };

        check_amount_reconciliation(&mut bill);

        assert_eq!(bill.total_flags(), 0, "cent-level rounding should be tolerated");
    }
}