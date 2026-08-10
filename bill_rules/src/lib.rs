//! # bill_rules
//!
//! Deterministic rules engine for medical bill analysis.
//!
//! This crate consumes structured medical bill data (mirroring the Python
//! backend's `ParsedBill` schema) and returns the same data enriched with
//! high-confidence flags for:
//!
//! - **Amount reconciliation** — math errors in allowed/paid/patient responsibility
//! - **Duplicate detection** — same CPT code + service date + similar charge
//! - **NCCI unbundling** — component codes billed alongside comprehensive codes
//!
//! The engine is pure, deterministic, and easy to extend with new rules.
//! It communicates with the Python backend via `serde`-compatible JSON.
//!
//! # Example
//!
//! ```rust
//! use bill_rules::{ParsedBill, apply_rules};
//!
//! let mut bill = ParsedBill::new("doc-123");
//! // ... populate bill with line items ...
//! let enriched = apply_rules(bill);
//! ```

pub mod engine;
pub mod rules;
pub mod types;

pub use engine::apply_rules;
pub use types::*;