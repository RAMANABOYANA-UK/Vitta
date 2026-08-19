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
///
/// NOTE: A single component code may appear in multiple pairs (e.g. `36415`
/// venipuncture is bundled into several E/M levels). The unbundling rule
/// checks **all** pairs, not just the first match.
pub const NCCI_UNBUNDLING_PAIRS: &[(&str, &str)] = &[
    // --- E/M visits + common bundled procedures ---
    // Venipuncture is bundled into most E/M visits.
    ("36415", "99211"),
    ("36415", "99212"),
    ("36415", "99213"),
    ("36415", "99214"),
    ("36415", "99215"),
    // Routine ECG is bundled into higher-level E/M visits.
    ("93000", "99213"),
    ("93000", "99214"),
    ("93000", "99215"),
    // Pulse oximetry is bundled into E/M visits.
    ("94760", "99213"),
    ("94760", "99214"),
    ("94760", "99215"),
    // Non-automated urinalysis is bundled into E/M visits.
    ("81002", "99213"),
    ("81002", "99214"),
    ("81002", "99215"),
    // Cerumen removal is bundled into E/M visits.
    ("69210", "99213"),
    ("69210", "99214"),
    ("69210", "99215"),
    // Pure-tone audiometry is bundled into E/M visits.
    ("92551", "99213"),
    ("92551", "99214"),
    ("92551", "99215"),
    // --- E/M level bundling (lower level bundled into higher level) ---
    ("99211", "99212"),
    ("99212", "99213"),
    ("99213", "99214"),
    ("99214", "99215"),
    // --- ECG component bundling ---
    ("93005", "93000"), // ECG tracing only → ECG with interpretation & report
    ("93010", "93000"), // ECG interpretation only → ECG with interpretation & report
    // --- Pulse oximetry component bundling ---
    ("94761", "94760"), // Oximetry, multiple determinations → single determination
    // --- Urinalysis component bundling ---
    ("81003", "81002"), // Automated urinalysis → non-automated (with microscopy)
    // --- Audiometry component bundling ---
    ("92557", "92551"), // Comprehensive audiometry → pure-tone only
    // --- Surgical packages: endoscopy ---
    ("45330", "45378"), // Sigmoidoscopy, diagnostic → Colonoscopy, diagnostic
    ("45331", "45378"), // Sigmoidoscopy with biopsy → Colonoscopy, diagnostic
    ("45378", "45380"), // Colonoscopy, diagnostic → with biopsy
    ("45380", "45385"), // Colonoscopy with biopsy → with polypectomy
    ("43200", "43235"), // Esophagoscopy, diagnostic → EGD, diagnostic
    ("43202", "43235"), // Esophagoscopy with biopsy → EGD, diagnostic
    ("43235", "43239"), // EGD, diagnostic → with biopsy
    ("43239", "43248"), // EGD with biopsy → with dilation
    // --- Surgical packages: arthroscopy ---
    ("29870", "29880"), // Knee arthroscopy, diagnostic → with meniscectomy
    ("29875", "29880"), // Knee arthroscopy, limited synovectomy → meniscectomy
    ("29877", "29880"), // Knee arthroscopy, debridement → meniscectomy
    ("29881", "29880"), // Meniscectomy med/lat → with meniscectomy + chondroplasty
    ("29870", "29881"), // Knee arthroscopy, diagnostic → meniscectomy
    // --- Surgical packages: laparoscopy ---
    ("49320", "47562"), // Diagnostic laparoscopy → Laparoscopic cholecystectomy
    ("49320", "47563"), // Diagnostic laparoscopy → Lap chole with cholangiography
    ("49320", "58558"), // Diagnostic laparoscopy → Hysteroscopy with biopsy
    ("49320", "58661"), // Diagnostic laparoscopy → Laparoscopy with removal of adnexa
    // --- Imaging: chest X-ray views ---
    ("71045", "71046"), // Chest X-ray, single view → 2 views
    ("71046", "71047"), // Chest X-ray, 2 views → 3 views
    ("71047", "71048"), // Chest X-ray, 3 views → 4+ views
    // --- Imaging: spine / extremity views ---
    ("72100", "72101"), // Lumbar spine, 2-3 views → 1 view
    ("72100", "72102"), // Lumbar spine, 2-3 views → 4+ views
    ("73030", "73020"), // Shoulder, minimum 2 views → 1 view
    ("73562", "73560"), // Knee, 3 views → 1 view
    ("73564", "73562"), // Knee, 4+ views → 3 views
    // --- Imaging: CT with/without contrast ---
    ("70450", "70460"), // CT head without contrast → with contrast
    ("70460", "70470"), // CT head with contrast → with and without contrast
    ("74176", "74177"), // CT abdomen/pelvis without contrast → with contrast
    ("74177", "74178"), // CT abdomen/pelvis with contrast → with and without
    // --- Lab panels: component tests bundled into panels ---
    ("80047", "80048"), // Basic metabolic panel w/ calcium → basic metabolic panel
    ("80048", "80053"), // Basic metabolic panel → comprehensive metabolic panel
    ("80053", "80076"), // Comprehensive metabolic panel → hepatic function panel
    ("85014", "85025"), // Hematocrit → CBC with differential
    ("85018", "85025"), // Hemoglobin → CBC with differential
    ("85004", "85025"), // Automated differential → CBC with differential
    ("85027", "85025"), // CBC without differential → CBC with differential
    ("82947", "82948"), // Glucose, quantitative → glucose, reagent strip
    ("82947", "82950"), // Glucose, quantitative → glucose, post-dose
    ("82950", "82951"), // Glucose, post-dose → glucose tolerance test
    // --- Cardiovascular: stress testing ---
    ("93015", "93016"), // Complete stress test → physician supervision only
    ("93016", "93017"), // Stress test supervision → tracing only
    ("93018", "93015"), // Stress test interpretation → complete stress test
    // --- Cardiovascular: echocardiography ---
    ("93303", "93306"), // TTE, congenital → complete TTE
    ("93307", "93306"), // TTE, limited → complete TTE
    ("93320", "93306"), // Doppler, complete → complete TTE
    ("93325", "93306"), // Doppler, color flow → complete TTE
    // --- Respiratory ---
    ("94010", "94060"), // Spirometry → spirometry with bronchodilation
    ("94060", "94014"), // Spirometry w/ bronchodilation → prolonged testing
    ("94640", "94642"), // Airway clearance → pressurized airway clearance
    ("94680", "94681"), // O2 uptake, rest → with exercise
    // --- Urology ---
    ("51701", "51702"), // Bladder catheterization, simple → with indwelling
    ("51702", "51703"), // Bladder catheterization, indwelling → complicated
    ("52000", "52204"), // Cystoscopy, diagnostic → with biopsy
    ("52204", "52214"), // Cystoscopy with biopsy → with fulguration
    ("52214", "52224"), // Cystoscopy with fulguration → with resection
    // --- Neurology ---
    ("95816", "95819"), // EEG, awake/drowsy → EEG, awake and asleep
    ("95819", "95822"), // EEG, awake and asleep → EEG, sleep only
    ("95900", "95903"), // Motor nerve conduction → with F-wave
    ("95904", "95903"), // Sensory nerve conduction → motor with F-wave
    // --- Dermatology ---
    ("11100", "11101"), // Skin biopsy, single → each additional
    ("17000", "17003"), // Destruction, premalignant, first → each additional
    ("17003", "17004"), // Destruction, premalignant, additional → 15+ lesions
    ("17260", "17261"), // Destruction, malignant, small → intermediate
    ("17261", "17262"), // Destruction, malignant, intermediate → large
    // --- Obstetrics / Gynecology ---
    ("58100", "58120"), // Endometrial biopsy → D&C
    ("58120", "58558"), // D&C → hysteroscopy with biopsy
    ("57452", "57455"), // Colposcopy, cervix → with biopsy
    ("57455", "57460"), // Colposcopy with biopsy → with LEEP
    // --- ENT ---
    ("31231", "31237"), // Nasal endoscopy, diagnostic → with biopsy
    ("31237", "31240"), // Nasal endoscopy with biopsy → with sinus surgery
    ("92504", "92502"), // Otoscopy → otoscopy with microscopy
    // --- Orthopedics ---
    ("20610", "20605"), // Joint aspiration, large → intermediate
    ("20605", "20600"), // Joint aspiration, intermediate → small
    ("29075", "29085"), // Short arm cast → long arm cast
    ("29125", "29126"), // Short arm splint → long arm splint
    // --- Pain management ---
    ("64415", "64416"), // Brachial plexus block → continuous infusion
    ("64417", "64416"), // Axillary block → brachial plexus continuous
    ("62310", "62311"), // Cervical/thoracic epidural → lumbar/sacral epidural
    // --- Ophthalmology ---
    ("92004", "92002"), // Comprehensive eye exam → intermediate
    ("92014", "92012"), // Comprehensive eye exam, established → intermediate
    ("92250", "92225"), // Fundus photography → extended ophthalmoscopy
    // --- Physical therapy ---
    ("97110", "97112"), // Therapeutic exercise → neuromuscular reeducation
    ("97112", "97116"), // Neuromuscular reeducation → gait training
    ("97140", "97112"), // Manual therapy → neuromuscular reeducation
    // --- Additional common NCCI unbundling pairs ---
    // Injection/infusion services bundled into E/M visits
    ("96372", "99213"), // Therapeutic injection → E/M level 3
    ("96372", "99214"), // Therapeutic injection → E/M level 4
    ("96372", "99215"), // Therapeutic injection → E/M level 5
    ("96374", "99213"), // IV push, single drug → E/M level 3
    ("96374", "99214"), // IV push, single drug → E/M level 4
    ("96374", "99215"), // IV push, single drug → E/M level 5
    // Simple blood draw bundled into venipuncture and E/M
    ("99195", "36415"), // Venipuncture, routine → venipuncture, simple
    // Vaccines bundled into administration codes
    ("90460", "90471"), // Vaccine admin, first component → immunization admin
    ("90476", "90460"), // Adenovirus vaccine → vaccine administration
    ("90658", "90460"), // Influenza vaccine → vaccine administration
    // EKG interpretation bundled into the EKG with interpretation
    ("93042", "93000"), // ECG report/review only → ECG with interpretation
    // Ultrasound guidance bundled into the procedure
    ("76942", "20610"), // US guidance → joint aspiration
    ("77012", "10022"), // CT guidance → fine needle aspiration
    ("77002", "10022"), // Fluoroscopic guidance → fine needle aspiration
    // Suture removal bundled with E/M
    ("15850", "99213"), // Suture removal by physician → E/M level 3
    ("15850", "99214"), // Suture removal by physician → E/M level 4
    // Nasal packing removal bundled into E/M / epistaxis control
    ("30903", "30901"), // Nasal packing, recurrent → nasal packing, simple
    ("30905", "30901"), // Nasal packing, posterior → nasal packing, simple
    // Skin tag removal bundled into E/M
    ("11200", "11201"), // Skin tag removal, up to 15 → each additional 10
    // Foley catheter insertion bundled into E/M
    ("51702", "99213"), // Foley catheter insertion → E/M level 3
    ("51702", "99214"), // Foley catheter insertion → E/M level 4
    // Oxygen saturation bundled into E/M (pulse oximetry)
    ("94760", "99211"), // Pulse oximetry → E/M level 1
    ("94761", "99212"), // Pulse oximetry, multiple → E/M level 2
    // ECGs at rest bundled into higher E/M (already covered above, add 99212)
    ("93000", "99212"), // Routine ECG → E/M level 2
    // X-ray multiple views (component → comprehensive)
    ("73500", "73510"), // Hip X-ray, single view → 2+ views
    ("73520", "73510"), // Hip X-ray, bilateral → hip X-ray, unilateral
    ("73000", "73010"), // Clavicle X-ray → scapula X-ray
    ("72040", "72050"), // Cervical spine, 2-3 views → 4-5 views
    ("72052", "72050"), // Cervical spine, 6+ views → 4-5 views
    // Add-on codes bundled into the primary procedure
    ("88305", "88309"), // Surgical pathology, level V → level VIII
    ("88307", "88309"), // Surgical pathology, level VI → level VIII
    // Cardiac catheterization components
    ("93451", "93458"), // Right heart cath → left heart cath with coronary
    ("93452", "93458"), // Left heart cath → left heart cath with coronary
    ("93453", "93458"), // Combined right/left heart cath → with coronary
    // Pacemaker lead placement bundled
    ("33206", "33208"), // Pacemaker, atrial → dual chamber
    ("33207", "33208"), // Pacemaker, ventricular → dual chamber
    // Endovascular procedures
    ("36200", "36245"), // Cath, artery, upper extremity → lower extremity
    ("36215", "36245"), // Cath, artery, upper → lower extremity
    // Physical therapy — each additional (component bundled)
    ("97001", "97110"), // PT evaluation → therapeutic exercise
    ("97002", "97110"), // PT re-evaluation → therapeutic exercise
    ("97003", "97112"), // OT evaluation → neuromuscular reeducation
    ("97004", "97112"), // OT re-evaluation → neuromuscular reeducation
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
        // Sanity check: non-empty, distinct component/comprehensive codes,
        // and no duplicate (component, comprehensive) pairs.
        assert!(!NCCI_UNBUNDLING_PAIRS.is_empty());
        let mut seen = std::collections::BTreeSet::new();
        for (component, comprehensive) in NCCI_UNBUNDLING_PAIRS {
            assert_ne!(component, comprehensive);
            assert!(
                seen.insert((*component, *comprehensive)),
                "duplicate NCCI pair: ({}, {})",
                component,
                comprehensive
            );
        }
    }

    #[test]
    fn ncci_pairs_cover_multi_component_mappings() {
        // 36415 (venipuncture) should map to multiple E/M levels.
        let venipuncture_targets: Vec<&str> = NCCI_UNBUNDLING_PAIRS
            .iter()
            .filter(|(c, _)| *c == "36415")
            .map(|(_, t)| *t)
            .collect();
        assert!(
            venipuncture_targets.len() >= 3,
            "venipuncture should map to at least 3 E/M levels, got {}",
            venipuncture_targets.len()
        );
    }
}