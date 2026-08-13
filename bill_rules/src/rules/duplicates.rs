use crate::types::{Flag, LineItem};

pub fn detect_duplicates(line_items: &mut [LineItem]) {
    let snapshot: Vec<(usize, Option<String>, Option<String>)> = line_items
        .iter()
        .enumerate()
        .map(|(i, item)| (i, item.cpt_hcpcs.clone(), item.service_date.clone()))
        .collect();

    for a in 0..snapshot.len() {
        for b in (a + 1)..snapshot.len() {
            let (idx_a, cpt_a, date_a) = &snapshot[a];
            let (idx_b, cpt_b, date_b) = &snapshot[b];

            let (Some(cpt_a), Some(cpt_b)) = (cpt_a, cpt_b) else { continue };
            if cpt_a != cpt_b { continue; }

            let same_date = match (date_a, date_b) {
                (Some(d1), Some(d2)) => Some(d1 == d2),
                _ => None,
            };

            let (severity, message) = match same_date {
                Some(true) => ("high", format!(
                    "Likely duplicate: CPT {} billed twice on the same date of service.", cpt_a)),
                Some(false) => continue,
                None => ("medium", format!(
                    "Possible duplicate: CPT {} appears more than once (dates could not be confirmed as different).", cpt_a)),
            };

            let flag = Flag {
                r#type: "duplicate".to_string(),
                severity: severity.to_string(),
                message,
                rule_id: Some("DUP-CPT-001".to_string()),
                shap_contribution: None,
            };

            for idx in [*idx_a, *idx_b] {
                if !line_items[idx].flags.iter().any(|f| f.rule_id == flag.rule_id && f.message == flag.message) {
                    line_items[idx].flags.push(flag.clone());
                }
            }
        }
    }
}