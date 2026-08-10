//! Demo: Run the rules engine on a sample medical bill.
//!
//! Build and run with:
//! ```bash
//! cargo run --example demo
//! ```

use bill_rules::{apply_rules, LineItem, ParsedBill, Totals};

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
    }
}

fn main() {
    // Build a realistic bill with intentional issues:
    // 1. Duplicate ECG (93000) with identical charge
    // 2. Sigmoidoscopy (45330) + Colonoscopy (45378) → NCCI unbundling
    // 3. Math error: patient responsibility doesn't match allowed - paid
    let bill = ParsedBill {
        document_id: "demo-bill-001".to_string(),
        status: "processing".to_string(),
        service_date: None,
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
    println!("Input: {} line items, billed ${:.2}", bill.line_item_count(), bill.totals.billed);

    // Run the rules engine
    let result = apply_rules(bill);

    println!("\n--- Detected Flags ---\n");

    let mut flag_count = 0;
    for item in &result.line_items {
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
        println!("Total: {} flag(s) detected across {} line item(s).", flag_count, result.line_item_count());
    }

    // Demonstrate serde serialization for Python backend integration
    println!("\n--- JSON Output (for Python backend) ---\n");
    let json = serde_json::to_string_pretty(&result).expect("serialization failed");
    println!("{}", json);
}