use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Flag {
    pub r#type: String,
    pub severity: String,
    pub message: String,
    pub rule_id: Option<String>,
    pub shap_contribution: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LineItem {
    pub id: String,
    #[serde(default = "default_page")]
    pub page: u32,
    pub description: String,
    pub cpt_hcpcs: Option<String>,
    #[serde(default)]
    pub icd10: Vec<String>,
    #[serde(default = "default_units")]
    pub units: f64,
    pub charge_amount: f64,
    pub allowed_amount: Option<f64>,
    pub paid_amount: Option<f64>,
    pub patient_responsibility: Option<f64>,
    #[serde(default)]
    pub modifiers: Vec<String>,
    #[serde(default)]
    pub flags: Vec<Flag>,
    #[serde(default)]
    pub service_date: Option<String>,
}

fn default_page() -> u32 { 1 }
fn default_units() -> f64 { 1.0 }

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Totals {
    pub billed: f64,
    pub allowed: Option<f64>,
    pub insurance_paid: Option<f64>,
    pub patient_responsibility: Option<f64>,
    pub potential_savings: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RuleInput {
    #[serde(default)]
    pub line_items: Vec<LineItem>,
    #[serde(default)]
    pub totals: Totals,
}

impl RuleInput {
    pub fn total_flags(&self) -> usize {
        self.line_items.iter().map(|i| i.flags.len()).sum()
    }
}

pub const NCCI_UNBUNDLING_PAIRS: &[(&str, &str)] = &[
    ("36415", "99211"),
    ("87880", "87070"),
    ("99213", "99214"),
    ("29881", "29880"),
];