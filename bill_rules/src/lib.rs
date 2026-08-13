pub mod engine;
pub mod rules;
pub mod types;

use serde_json::Value;
use thiserror::Error;
use types::{RuleInput, Totals};

#[derive(Debug, Error)]
pub enum EngineError {
    #[error("input document is not a JSON object")]
    NotAnObject,
    #[error("failed to parse line_items: {0}")]
    LineItemsParse(serde_json::Error),
    #[error("failed to parse totals: {0}")]
    TotalsParse(serde_json::Error),
    #[error("failed to serialize enriched line_items: {0}")]
    Serialize(serde_json::Error),
}

pub fn apply_rules_to_document(mut doc: Value) -> Result<Value, EngineError> {
    let obj = doc.as_object_mut().ok_or(EngineError::NotAnObject)?;

    let line_items_value = obj.get("line_items").cloned().unwrap_or(Value::Array(vec![]));
    let totals_value = obj.get("totals").cloned().unwrap_or(Value::Null);

    let line_items = serde_json::from_value(line_items_value).map_err(EngineError::LineItemsParse)?;
    let totals: Totals = if totals_value.is_null() {
        Totals::default()
    } else {
        serde_json::from_value(totals_value).map_err(EngineError::TotalsParse)?
    };

    let input = RuleInput { line_items, totals };
    let enriched = engine::apply_rules(input);

    let enriched_line_items = serde_json::to_value(&enriched.line_items).map_err(EngineError::Serialize)?;
    obj.insert("line_items".to_string(), enriched_line_items);

    Ok(doc)
}