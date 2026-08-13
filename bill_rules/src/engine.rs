use crate::rules::{duplicates, reconciliation, unbundling};
use crate::types::RuleInput;

pub fn apply_rules(mut input: RuleInput) -> RuleInput {
    reconciliation::check_line_item_reconciliation(&mut input.line_items);

    if let Some(totals_flag) = reconciliation::check_totals_reconciliation(&input.line_items, &input.totals) {
        if let Some(first) = input.line_items.first_mut() {
            first.flags.push(totals_flag);
        }
    }

    duplicates::detect_duplicates(&mut input.line_items);
    unbundling::detect_unbundling(&mut input.line_items);

    input
}