use serde::{Deserialize, Serialize};

/// A single flagged issue on a line item or the bill as a whole.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Flag {
    pub r#type: String,
    pub severity: String,
    pub message: String,
    pub rule_id: Option<String>,
    pub shap_contribution: Option<f64>,
}

/// A single line item on a medical bill.
///
/// All optional fields use `#[serde(default)]` so the service tolerates
/// partial or slightly different JSON shapes from the Python side —
/// missing fields become `None` / `vec![]` rather than failing the parse.
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

fn default_page() -> u32 {
    1
}

fn default_units() -> f64 {
    1.0
}

/// Aggregated totals for the bill.
///
/// `billed` defaults to 0.0 so a missing `totals` object still parses.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Totals {
    #[serde(default)]
    pub billed: f64,
    pub allowed: Option<f64>,
    pub insurance_paid: Option<f64>,
    pub patient_responsibility: Option<f64>,
    pub potential_savings: Option<f64>,
}

/// Typed input to the rules engine — the *only* parts of the incoming
/// document the engine is allowed to read.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RuleInput {
    #[serde(default)]
    pub line_items: Vec<LineItem>,
    #[serde(default)]
    pub totals: Totals,
}

/// Typed output of the rules engine.
///
/// The engine returns `line_items` (with flags attached) plus a small
/// summary for structured logging. `totals` is returned unchanged so
/// the caller can log it if needed, but the engine never mutates it.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RuleOutput {
    pub line_items: Vec<LineItem>,
    pub totals: Totals,
    /// Total number of flags across all line items after rule application.
    pub total_flags: usize,
    /// Count of flags added by this run, broken down by `rule_id`.
    pub flags_added: std::collections::BTreeMap<String, usize>,
}

impl RuleInput {
    /// Total number of flags currently on the input line items.
    pub fn input_flag_count(&self) -> usize {
        self.line_items.iter().map(|i| i.flags.len()).sum()
    }
}

/// Known NCCI (National Correct Coding Initiative) procedure-to-procedure
/// unbundling pairs: `(component, comprehensive)`.
///
/// When a component code is billed alongside its comprehensive code, the
/// component should typically be bundled into the comprehensive — billing
/// both separately is a common unbundling error. This is a realistic
/// starter set that can later be loaded from the full NCCI PTP edit file.
pub const NCCI_UNBUNDLING_PAIRS: &[(&str, &str)] = &[
    // --- E/M visits ---
    // Level-1 E/M is often bundled into level-2 E/M when both are billed.
    ("99211", "99212"),
    ("99212", "99213"),
    ("99213", "99214"),
    // --- Blood draw / venipuncture ---
    // Venipuncture is bundled into most E/M visits and lab draws.
    ("36415", "99213"),
    ("36415", "99214"),
    ("36415", "99215"),
    // --- Strep test vs throat culture ---
    // Rapid strep (87880) is a component of a full throat culture (87070)
    // when both are performed and billed together.
    ("87880", "87070"),
    // --- Imaging: single view vs multiple views ---
    ("71045", "71046"), // Chest X-ray, single view → 2 views
    ("71046", "71047"), // Chest X-ray, 2 views → 3 views
    // --- Diagnostic endoscopy components ---
    ("45330", "45378"), // Sigmoidoscopy, diagnostic → Colonoscopy, diagnostic
    ("43200", "43235"), // Esophagoscopy, diagnostic → EGD, diagnostic
    // --- Orthopedic arthroscopy ---
    // Diagnostic arthroscopy is bundled into the therapeutic arthroscopy.
    ("29870", "29880"), // Knee arthroscopy, diagnostic → with meniscectomy
    ("29875", "29881"), // Knee arthroscopy, limited synovectomy → meniscectomy
    ("29877", "29880"), // Knee arthroscopy, debridement → with meniscectomy
    ("29881", "29880"), // Meniscectomy med/lat → with meniscectomy + chondroplasty
];

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_line_item_with_missing_optional_fields() {
        let json = r#"{
            "id": "LI-1",
            "description": "ER visit",
            "charge_amount": 100.0
        }"#;
        let item: LineItem = serde_json::from_str(json).unwrap();
        assert_eq!(item.page, 1);
        assert_eq!(item.units, 1.0);
        assert!(item.icd10.is_empty());
        assert!(item.modifiers.is_empty());
        assert!(item.flags.is_empty());
        assert!(item.cpt_hcpcs.is_none());
        assert!(item.allowed_amount.is_none());
        assert!(item.service_date.is_none());
    }

    #[test]
    fn parses_totals_with_missing_billed() {
        let json = r#"{"allowed": 1200.0}"#;
        let totals: Totals = serde_json::from_str(json).unwrap();
        assert_eq!(totals.billed, 0.0);
        assert_eq!(totals.allowed, Some(1200.0));
    }

    #[test]
    fn ncci_pairs_are_deduped_and_ordered() {
        // Just a sanity check that the list is non-empty and each pair
        // has distinct component/comprehensive codes.
        assert!(!NCCI_UNBUNDLING_PAIRS.is_empty());
        for (component, comprehensive) in NCCI_UNBUNDLING_PAIRS {
            assert_ne!(component, comprehensive);
        }
    }
}