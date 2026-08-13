use crate::types::{Flag, LineItem, NCCI_UNBUNDLING_PAIRS};

pub fn detect_unbundling(line_items: &mut [LineItem]) {
    let snapshot: Vec<(usize, Option<String>)> = line_items
        .iter().enumerate().map(|(i, item)| (i, item.cpt_hcpcs.clone())).collect();

    for a in 0..snapshot.len() {
        for b in 0..snapshot.len() {
            if a == b { continue; }
            let (_idx_a, Some(cpt_a)) = (&snapshot[a].0, &snapshot[a].1) else { continue };
            let (idx_b, Some(cpt_b)) = (&snapshot[b].0, &snapshot[b].1) else { continue };

            let is_pair = NCCI_UNBUNDLING_PAIRS.iter()
                .any(|(primary, secondary)| primary == cpt_a && secondary == cpt_b);

            if is_pair {
                let flag = Flag {
                    r#type: "unbundling".to_string(),
                    severity: "high".to_string(),
                    message: format!(
                        "CPT {} is typically bundled into CPT {} per NCCI edits and shouldn't usually be billed separately.",
                        cpt_b, cpt_a),
                    rule_id: Some(format!("NCCI-{}-{}", cpt_a, cpt_b)),
                    shap_contribution: None,
                };
                if !line_items[*idx_b].flags.iter().any(|f| f.rule_id == flag.rule_id) {
                    line_items[*idx_b].flags.push(flag);
                }
            }
        }
    }
}