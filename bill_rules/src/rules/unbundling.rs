use crate::types::{Flag, ParsedBill, Severity};

/// Rule ID for NCCI unbundling detection.
const RULE_NCCI_UNBUNDLE: &str = "NCCI-UNBUNDLE-001";

/// Known NCCI unbundling pairs: (component, comprehensive).
///
/// When a component code is billed alongside its comprehensive code,
/// the component should be bundled into the comprehensive — billing both
/// separately is a common unbundling error.
///
/// This is a small starter set. In production this would be loaded from
/// the full NCCI PTP (Procedure-to-Procedure) edit file.
const NCCI_PAIRS: &[(&str, &str)] = &[
    // Colonoscopy (comprehensive) vs. sigmoidoscopy (component)
    ("45330", "45378"), // Sigmoidoscopy, diagnostic → Colonoscopy, diagnostic
    ("45331", "45378"), // Sigmoidoscopy with biopsy → Colonoscopy, diagnostic
    // EGD (comprehensive) vs. esophagoscopy (component)
    ("43200", "43235"), // Esophagoscopy, diagnostic → EGD, diagnostic
    // Chest X-ray (comprehensive) vs. single view (component)
    ("71045", "71046"), // Chest X-ray, single view → Chest X-ray, 2 views
    // CBC (comprehensive) vs. individual components
    ("85014", "85025"), // Hematocrit → CBC with differential
    ("85018", "85025"), // Hemoglobin → CBC with differential
    // Office visit (comprehensive) vs. minor procedures
    ("99211", "99213"), // Level 1 visit → Level 3 visit
];

/// Detect NCCI unbundling: component code billed alongside its comprehensive code.
///
/// Flags both the component and comprehensive line items with a warning,
/// since the component charge should typically be bundled into the
/// comprehensive service.
pub fn detect_unbundling(bill: &mut ParsedBill) {
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

            // Check both directions: (a is component, b is comprehensive) and vice versa
            let is_unbundled = NCCI_PAIRS.iter().any(|(component, comprehensive)| {
                (cpt_a == *component && cpt_b == *comprehensive)
                    || (cpt_b == *component && cpt_a == *comprehensive)
            });

            if !is_unbundled {
                continue;
            }

            // Determine which is the component and which is the comprehensive
            let (component_cpt, comprehensive_cpt) = if NCCI_PAIRS
                .iter()
                .any(|(c, comp)| cpt_a == *c && cpt_b == *comp)
            {
                (cpt_a, cpt_b)
            } else {
                (cpt_b, cpt_a)
            };

            let flag = Flag::new(
                "unbundling",
                Severity::Warning,
                format!(
                    "Possible NCCI unbundling: CPT {} (component) should be bundled into CPT {} (comprehensive).",
                    component_cpt, comprehensive_cpt
                ),
                RULE_NCCI_UNBUNDLE,
            );

            // Flag both items
            if let Some(line) = bill.line_items.get_mut(i) {
                if !line.flags.iter().any(|f| f.rule_id == Some(RULE_NCCI_UNBUNDLE.to_string())) {
                    line.flags.push(flag.clone());
                }
            }
            if let Some(line) = bill.line_items.get_mut(j) {
                if !line.flags.iter().any(|f| f.rule_id == Some(RULE_NCCI_UNBUNDLE.to_string())) {
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
            document_id: "test".to_string(),
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
    fn detects_unbundling_pair() {
        // Sigmoidoscopy (45330) + Colonoscopy (45378) — should be flagged
        let mut bill = make_bill(vec![
            make_item("1", "45330", 500.0),
            make_item("2", "45378", 2100.0),
        ]);

        detect_unbundling(&mut bill);

        let flags = bill.flags_of_type("unbundling");
        assert_eq!(flags.len(), 2, "both items should be flagged");
        assert_eq!(flags[0].rule_id.as_deref(), Some(RULE_NCCI_UNBUNDLE));
        assert!(
            flags[0].message.contains("45330"),
            "message should mention the component CPT"
        );
    }

    #[test]
    fn no_flag_for_unrelated_cpts() {
        let mut bill = make_bill(vec![
            make_item("1", "99285", 1000.0),
            make_item("2", "80053", 150.0),
        ]);

        detect_unbundling(&mut bill);

        assert_eq!(bill.total_flags(), 0);
    }

    #[test]
    fn detects_reverse_order_pair() {
        // Colonoscopy (45378) billed before Sigmoidoscopy (45330)
        let mut bill = make_bill(vec![
            make_item("1", "45378", 2100.0),
            make_item("2", "45330", 500.0),
        ]);

        detect_unbundling(&mut bill);

        assert_eq!(bill.flags_of_type("unbundling").len(), 2);
    }

    #[test]
    fn no_flag_when_only_component_present() {
        // Only the component code, no comprehensive — not an unbundling issue
        let mut bill = make_bill(vec![make_item("1", "45330", 500.0)]);

        detect_unbundling(&mut bill);

        assert_eq!(bill.total_flags(), 0);
    }
}