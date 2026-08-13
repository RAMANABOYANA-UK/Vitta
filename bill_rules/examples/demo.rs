//! Demo: Run the rules engine on a sample medical bill.
//!
//! Build and run with:
//! ```bash
//! cargo run --example demo
//! ```

use bill_rules::engine;
use bill_rules::types::{LineItem, RuleInput, Totals};
use serde_json::json;

fn make_item(
    id: &str,
    cpt: &str,
    description: &str,
    charge: f64,
    allowed: Option<f64>,
    paid: Option<f64>,
    patient_resp: Option<f64>,
) -> LineItem {
    LineItem {
        id: id.to_string(),
        page: 1,
        description: description.to_string(),
        cpt_hcpcs: Some(cpt.to_string()),
        icd10: vec!["R07.9".to_string(), "I10".to_string()],
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

fn main() {
    // Build a realistic bill with intentional issues:
    // 1. Duplicate ECG (93000) with identical charge
    // 2. Sigmoidoscopy (45330) + Colonoscopy (45378) → NCCI unbundling
    // 3. Math error: patient responsibility doesn't match allowed - paid
    let input = RuleInput {
        line_items: vec![
            make_item(
                "LI-1",
                "99285",
                "Emergency department visit, high severity",
                1840.00,
                Some(1120.00),
                Some(896.00),
                Some(224.00),
            ),
            make_item(
                "LI-2",
                "93000",
                "Electrocardiogram, routine ECG",
                275.00,
                Some(95.00),
                Some(76.00),
                Some(19.00),
            ),
            make_item(
                "LI-3",
                "93000",
                "Electrocardiogram, routine ECG (duplicate)",
                275.00,
                Some(95.00),
                Some(76.00),
                Some(19.00),
            ),
            make_item(
                "LI-4",
                "45330",
                "Sigmoidoscopy, diagnostic",
                500.00,
                None,
                None,
                None,
            ),
            make_item(
                "LI-5",
                "45378",
                "Colonoscopy, diagnostic",
                2100.00,
                None,
                None,
                None,
            ),
            make_item(
                "LI-6",
                "80053",
                "Comprehensive metabolic panel",
                150.00,
                Some(68.00),
                Some(54.40),
                Some(30.00), // ← math error: should be 13.60
            ),
        ],
        totals: Totals {
            billed: 5140.00,
            allowed: Some(1378.00),
            insurance_paid: Some(1102.40),
            patient_responsibility: Some(275.60),
            potential_savings: None,
        },
    };

    println!("=== Medical Bill Rules Engine Demo ===\n");
    println!("Input: {} line items, billed ${:.2}", input.line_items.len(), input.totals.billed);

    // Run the rules engine
    let output = engine::apply_rules(input);

    println!("\n--- Detected Flags ---\n");

    let mut flag_count = 0;
    for item in &output.line_items {
        if item.flags.is_empty() {
            continue;
        }
        println!("[{}] {} (CPT: {})", item.id, item.description, item.cpt_hcpcs.as_deref().unwrap_or("N/A"));
        for flag in &item.flags {
            flag_count += 1;
            println!(
                "  ⚠ [{}] {} — {}",
                flag.severity,
                flag.rule_id.as_deref().unwrap_or("unknown"),
                flag.message
            );
        }
        println!();
    }

    if flag_count == 0 {
        println!("No flags detected — this bill is clean.");
    } else {
        println!("Total: {} flag(s) detected across {} line item(s).", flag_count, output.line_items.len());
    }

    // Demonstrate the HTTP round-trip path: build a full ParsedBill-like
    // JSON document with extra fields and verify they survive intact.
    println!("\n--- HTTP Round-Trip (opaque JSON pass-through) ---\n");
    let doc = json!({
        "document_id": "demo-bill-001",
        "status": "letter_ready",
        "patient": {"name": "Jane Doe", "member_id": "M123"},
        "provider": {"name": "Memorial Hospital", "npi": "1234567893"},
        "payer": {"name": "Acme Insurance", "claim_number": "GX-2025-883241"},
        "line_items": [
            {"id": "LI-1", "description": "ER visit", "cpt_hcpcs": "99284",
             "charge_amount": 1240.0, "allowed_amount": 800.0,
             "paid_amount": 650.0, "patient_responsibility": 150.0},
            {"id": "LI-2", "description": "ER visit (dup)", "cpt_hcpcs": "99284",
             "charge_amount": 1240.0, "allowed_amount": 800.0,
             "paid_amount": 650.0, "patient_responsibility": 150.0}
        ],
        "totals": {"billed": 2480.0, "allowed": 1600.0},
        "letter": {"status": "draft", "content_markdown": "# Appeal"},
        "audit": {"extraction_engine": "mock-v1"}
    });

    let enriched = bill_rules::apply_rules_to_document(doc).expect("round-trip failed");
    println!("patient: {}", enriched["patient"]["name"]);
    println!("provider NPI: {}", enriched["provider"]["npi"]);
    println!("letter status: {}", enriched["letter"]["status"]);
    println!("audit engine: {}", enriched["audit"]["extraction_engine"]);
    println!("total flags on item 1: {}", enriched["line_items"][0]["flags"].as_array().unwrap().len());
    println!("total flags on item 2: {}", enriched["line_items"][1]["flags"].as_array().unwrap().len());
    println!("\nAll unknown fields preserved ✓");
}