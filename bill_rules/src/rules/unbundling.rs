use crate::types::{Flag, LineItem, NCCI_UNBUNDLING_PAIRS};

/// Detect NCCI unbundling: a *component* code billed alongside its
/// *comprehensive* code.
///
/// Pair format: `(component, comprehensive)`.
///
/// When both codes appear on the same bill, the component (e.g. a
/// venipuncture, a sigmoidoscopy) is typically considered already
/// included in the comprehensive service (e.g. the E/M visit, the
/// colonoscopy). Billing both separately is a common unbundling error.
///
/// The flag is attached to the **component** item, with a message that
/// names both codes. Flags are deduplicated by `rule_id`.
pub fn detect_unbundling(line_items: &mut [LineItem]) {
    // Snapshot the CPT codes before mutating flags.
    let snapshot: Vec<(usize, Option<String>)> = line_items
        .iter()
        .enumerate()
        .map(|(i, item)| (i, item.cpt_hcpcs.clone()))
        .collect();

    for a in 0..snapshot.len() {
        let (idx_a, Some(cpt_a)) = (&snapshot[a].0, &snapshot[a].1) else {
            continue;
        };

        // Is cpt_a the component side of any known pair?
        let Some((_, comprehensive)) = NCCI_UNBUNDLING_PAIRS
            .iter()
            .find(|(component, _)| component == cpt_a)
        else {
            continue;
        };

        // Is the comprehensive code also present on the bill (any item
        // other than the component item itself)?
        let comprehensive_present = snapshot.iter().any(|(idx_b, cpt_b)| {
            idx_b != idx_a && cpt_b.as_deref() == Some(comprehensive)
        });

        if !comprehensive_present {
            continue;
        }

        let rule_id = format!("NCCI-{}-{}", cpt_a, comprehensive);

        let flag = Flag {
            r#type: "unbundling".to_string(),
            severity: "high".to_string(),
            message: format!(
                "CPT {} is typically bundled into CPT {} per NCCI edits and shouldn't usually be billed separately.",
                cpt_a, comprehensive
            ),
            rule_id: Some(rule_id.clone()),
            shap_contribution: None,
        };

        if let Some(item) = line_items.get_mut(*idx_a) {
            if !item.flags.iter().any(|f| f.rule_id == Some(rule_id.clone())) {
                item.flags.push(flag);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
            service_date: None,
        }
    }

    #[test]
    fn detects_component_with_comprehensive() {
        // 36415 (venipuncture, component) + 99213 (level-3 E/M, comprehensive)
        let mut items = vec![
            make_item("1", "36415", 25.0),
            make_item("2", "99213", 150.0),
        ];
        detect_unbundling(&mut items);

        // Flag should be on the component item (1), not the comprehensive (2).
        assert_eq!(items[0].flags.len(), 1);
        assert!(items[1].flags.is_empty());

        let f = &items[0].flags[0];
        assert_eq!(f.rule_id.as_deref(), Some("NCCI-36415-99213"));
        assert_eq!(f.severity, "high");
        assert!(f.message.contains("36415"));
        assert!(f.message.contains("99213"));
        assert!(f.message.contains("bundled"));
    }

    #[test]
    fn detects_when_comprehensive_comes_first() {
        // Order shouldn't matter: comprehensive listed before component.
        let mut items = vec![
            make_item("1", "99213", 150.0),
            make_item("2", "36415", 25.0),
        ];
        detect_unbundling(&mut items);
        assert_eq!(items[1].flags.len(), 1);
        assert!(items[0].flags.is_empty());
    }

    #[test]
    fn no_flag_when_only_component_present() {
        let mut items = vec![make_item("1", "36415", 25.0)];
        detect_unbundling(&mut items);
        assert!(items[0].flags.is_empty());
    }

    #[test]
    fn no_flag_when_only_comprehensive_present() {
        let mut items = vec![make_item("1", "99213", 150.0)];
        detect_unbundling(&mut items);
        assert!(items[0].flags.is_empty());
    }

    #[test]
    fn flags_are_deduplicated() {
        // Even with multiple passes of the same pair, the flag shouldn't stack.
        let mut items = vec![
            make_item("1", "36415", 25.0),
            make_item("2", "99213", 150.0),
        ];
        detect_unbundling(&mut items);
        detect_unbundling(&mut items);
        assert_eq!(items[0].flags.len(), 1);
    }
}