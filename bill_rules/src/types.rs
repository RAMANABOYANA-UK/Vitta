use chrono::NaiveDate;
use serde::{Deserialize, Serialize};

/// Severity levels for flags, mirroring the Python backend contract.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Info,
    Warning,
    Critical,
    High,
}

impl Severity {
    pub fn as_str(&self) -> &'static str {
        match self {
            Severity::Info => "info",
            Severity::Warning => "warning",
            Severity::Critical => "critical",
            Severity::High => "high",
        }
    }
}

impl From<Severity> for String {
    fn from(severity: Severity) -> Self {
        severity.as_str().to_string()
    }
}

/// A single flagged issue on a line item or the bill as a whole.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Flag {
    pub r#type: String,
    pub severity: String,
    pub message: String,
    pub rule_id: Option<String>,
    pub shap_contribution: Option<f64>,
}

impl Flag {
    pub fn new(r#type: &str, severity: Severity, message: impl Into<String>, rule_id: &str) -> Self {
        Self {
            r#type: r#type.to_string(),
            severity: severity.as_str().to_string(),
            message: message.into(),
            rule_id: Some(rule_id.to_string()),
            shap_contribution: None,
        }
    }
}

/// A single line item on a medical bill.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LineItem {
    pub id: String,
    pub page: u32,
    pub description: String,
    pub cpt_hcpcs: Option<String>,
    pub icd10: Vec<String>,
    pub units: f64,
    pub charge_amount: f64,
    pub allowed_amount: Option<f64>,
    pub paid_amount: Option<f64>,
    pub patient_responsibility: Option<f64>,
    pub modifiers: Vec<String>,
    pub flags: Vec<Flag>,
}

/// Aggregated totals for the bill.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Totals {
    pub billed: f64,
    pub allowed: Option<f64>,
    pub insurance_paid: Option<f64>,
    pub patient_responsibility: Option<f64>,
    pub potential_savings: Option<f64>,
}

/// The subset of the bill structure the rules engine operates on.
///
/// This mirrors the `ParsedBill` schema from the Python backend (app/schemas.py)
/// but only includes the fields needed for deterministic rule evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParsedBill {
    pub document_id: String,
    pub status: String,
    pub service_date: Option<NaiveDate>,
    pub line_items: Vec<LineItem>,
    pub totals: Totals,
}

impl ParsedBill {
    /// Create a new, empty ParsedBill with a generated document id.
    pub fn new(document_id: impl Into<String>) -> Self {
        Self {
            document_id: document_id.into(),
            status: "processing".to_string(),
            service_date: None,
            line_items: Vec::new(),
            totals: Totals {
                billed: 0.0,
                allowed: None,
                insurance_paid: None,
                patient_responsibility: None,
                potential_savings: None,
            },
        }
    }

    /// Number of line items on the bill.
    pub fn line_item_count(&self) -> usize {
        self.line_items.len()
    }

    /// Total number of flags across all line items.
    pub fn total_flags(&self) -> usize {
        self.line_items.iter().map(|item| item.flags.len()).sum()
    }

    /// Collect references to any flags of a given type across all items.
    pub fn flags_of_type(&self, flag_type: &str) -> Vec<&Flag> {
        self.line_items
            .iter()
            .flat_map(|item| item.flags.iter())
            .filter(|flag| flag.r#type == flag_type)
            .collect()
    }
}