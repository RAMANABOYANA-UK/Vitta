use crate::types::{Flag, LineItem, Totals};

const TOLERANCE_CENTS: f64 = 0.05;

pub fn check_line_item_reconciliation(line_items: &mut [LineItem]) {
    for item in line_items.iter_mut() {
        let (Some(allowed), Some(paid), Some(patient_resp)) =
            (item.allowed_amount, item.paid_amount, item.patient_responsibility) else { continue };

        let expected_patient = (allowed - paid).max(0.0);
        let difference = (patient_resp - expected_patient).abs();

        if difference > TOLERANCE_CENTS {
            item.flags.push(Flag {
                r#type: "math_error".to_string(),
                severity: "high".to_string(),
                message: format!(
                    "Amount mismatch: allowed (${:.2}) minus paid (${:.2}) should leave ~${:.2} patient responsibility, but ${:.2} was charged.",
                    allowed, paid, expected_patient, patient_resp),
                rule_id: Some("MATH-RECON-001".to_string()),
                shap_contribution: None,
            });
        }
    }
}

pub fn check_totals_reconciliation(line_items: &[LineItem], totals: &Totals) -> Option<Flag> {
    let sum_charges: f64 = line_items.iter().map(|i| i.charge_amount).sum();
    let difference = (sum_charges - totals.billed).abs();

    if difference > 1.0 {
        Some(Flag {
            r#type: "math_error".to_string(),
            severity: "medium".to_string(),
            message: format!(
                "Line items sum to ${:.2}, but the bill's stated total is ${:.2}.",
                sum_charges, totals.billed),
            rule_id: Some("MATH-RECON-TOTALS-001".to_string()),
            shap_contribution: None,
        })
    } else {
        None
    }
}