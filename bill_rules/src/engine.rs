use crate::rules::{duplicates, reconciliation, unbundling};
use crate::types::{RuleInput, RuleOutput};

/// The main entry point for the rules engine.
///
/// Applied in a deliberate order:
/// 1. **Reconciliation** first — catches math errors that may affect the
///    interpretation of other rules.
/// 2. **Duplicates** — identifies double-billed services.
/// 3. **Unbundling** — identifies component codes billed alongside
///    comprehensive codes (NCCI).
///
/// The function is pure and deterministic: given the same input, it
/// always produces the same output. This is critical for reproducible
/// audit trails and testing.
pub fn apply_rules(mut input: RuleInput) -> RuleOutput {
    // Snapshot the (rule_id, message) pairs already present on the input
    // line items so we can report *newly added* flags (not pre-existing
    // engine flags from a prior run or mock data).
    let mut input_flag_keys = std::collections::BTreeSet::<(String, String)>::new();
    for item in input.line_items.iter() {
        for flag in item.flags.iter() {
            if let Some(rule_id) = flag.rule_id.as_deref() {
                input_flag_keys.insert((rule_id.to_string(), flag.message.clone()));
            }
        }
    }

    reconciliation::check_line_item_reconciliation(&mut input.line_items);

    if let Some(totals_flag) =
        reconciliation::check_totals_reconciliation(&input.line_items, &input.totals)
    {
        if let Some(first) = input.line_items.first_mut() {
            first.flags.push(totals_flag);
        }
    }

    duplicates::detect_duplicates(&mut input.line_items);
    unbundling::detect_unbundling(&mut input.line_items);

    // Count unique (rule_id, message) pairs that were *not* present on input —
    // flags actually added by this run. Flags applied to both items of a
    // duplicate pair share the same rule_id+message, so we dedupe by that key.
    let mut flags_added = std::collections::BTreeMap::<String, usize>::new();
    let mut seen = std::collections::BTreeSet::<(String, String)>::new();

    let total_flags: usize = input
        .line_items
        .iter()
        .flat_map(|item| item.flags.iter())
        .count();

    for item in input.line_items.iter() {
        for flag in item.flags.iter() {
            let Some(rule_id) = flag.rule_id.as_deref() else {
                continue;
            };

            let key = (rule_id.to_string(), flag.message.clone());
            if input_flag_keys.contains(&key) {
                continue; // pre-existing flag — not added by this run
            }

            let is_engine_rule = rule_id.starts_with("DUP-")
                || rule_id.starts_with("MATH-")
                || rule_id.starts_with("NCCI-");

            if is_engine_rule && seen.insert(key) {
                *flags_added.entry(rule_id.to_string()).or_insert(0) += 1;
            }
        }
    }

    RuleOutput {
        line_items: input.line_items,
        totals: input.totals,
        total_flags,
        flags_added,
    }
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
            service_date: None,
        }
    }

    fn make_bill(items: Vec<LineItem>) -> RuleInput {
        let billed: f64 = items.iter().map(|i| i.charge_amount).sum();
        RuleInput {
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
    fn runs_all_rules_and_counts_flags() {
        // 36415 + 99213 pair (unbundling) + duplicate 99213 with same charge.
        let input = make_bill(vec![
            make_item("1", "36415", 25.0, None, None, None),
            make_item("2", "99213", 150.0, Some(150.0), Some(120.0), Some(30.0)),
            make_item("3", "99213", 150.0, Some(150.0), Some(125.0), Some(25.0)),
        ]);

        let output = apply_rules(input);

        // 36415 gets 1 unbundling flag; both 99213 items get a duplicate flag
        // (same charge) → 3 flags total.
        assert_eq!(output.total_flags, 3);
        assert!(output.flags_added.contains_key("NCCI-36415-99213"));
        assert!(output.flags_added.contains_key("DUP-CPT-CHARGE-002"));
    }

    #[test]
    fn clean_bill_has_zero_flags() {
        let input = make_bill(vec![
            make_item("1", "99285", 1000.0, None, None, None),
            make_item("2", "80053", 150.0, None, None, None),
        ]);
        let output = apply_rules(input);
        assert_eq!(output.total_flags, 0);
        assert!(output.flags_added.is_empty());
    }

    #[test]
    fn preserves_line_item_count_and_totals() {
        let input = make_bill(vec![
            make_item("1", "99285", 1000.0, None, None, None),
            make_item("2", "80053", 150.0, None, None, None),
        ]);
        let output = apply_rules(input);
        assert_eq!(output.line_items.len(), 2);
        assert_eq!(output.totals.billed, 1150.0);
    }

    #[test]
    fn deterministic_output() {
        let build = || {
            make_bill(vec![
                make_item("1", "36415", 25.0, None, None, None),
                make_item("2", "99213", 150.0, Some(150.0), Some(120.0), Some(30.0)),
                make_item("3", "99213", 150.0, Some(150.0), Some(125.0), Some(25.0)),
            ])
        };

        let out_a = apply_rules(build());
        let out_b = apply_rules(build());

        let json_a = serde_json::to_string(&out_a.line_items).unwrap();
        let json_b = serde_json::to_string(&out_b.line_items).unwrap();
        assert_eq!(json_a, json_b, "rules engine must be deterministic");
    }
}