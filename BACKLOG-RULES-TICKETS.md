# Vitta — Rules Engine: Ticket Drafts

> Companion to `BACKLOG.md` (items #12–#15). Paste-ready drafts for a tracker.
> Line references are accurate as of 2026-08-26.

**Engine context.** There are two rule surfaces:
- **Rust** (`bill_rules`): an Axum HTTP service (`:3001`) running reconciliation →
  duplicates → NCCI unbundling, deterministic and pure
  (`bill_rules/src/engine.rs:16-41`, covered by `#[test]`).
- **Python** (`data-extraction-service/app/services/validation_service.py`):
  code *format* validation, reference-data lookups, and the recently-landed modifier
  appropriateness guard.

---

## Ticket #12 — Place-of-service (POS) validation rules

- **Priority:** Medium · **Owner:** Rules (Python + Rust) ·
  **Depends on:** schema wiring (below).

### Current state
`place_of_service` exists in the **Python** `ParsedBill` schema
(`data-extraction-service/app/models/parsed_bill.py:206`) and is already used for
scoring feature derivation (`scoring_service.py:236,292-294` maps POS → provider
type). But **no validation rules check POS consistency**: a POS that contradicts the
CPT code or the service setting is not flagged anywhere. The **Rust** `LineItem`
struct has no `place_of_service` field at all (`bill_rules/src/types.rs:19-34`), so
the deterministic engine cannot reason about it yet.

### Goal
Add POS validation: a bill whose line's place-of-service contradicts its CPT code
(and CMS POS definitions) is flagged conservatively, across both the Python
validation path and (if feasible) the Rust engine.

### Approach / scope
1. **Schema first** — add `place_of_service` to the Rust `LineItem`
   (`types.rs`), matching the Python field already present.
2. Define a curated CMS POS table (code → setting, e.g. `11` office, `23` ER,
   `21` inpatient, `81` lab) in one place both sides can use.
3. Python (`validation_service.py`): add conservative POS↔CPT checks, e.g.:
   - a `office` POS on an ED/OR-only CPT,
   - a lab/billing POS mismatching a lab service,
   - missing/unknown POS codes surfaced as a low-severity/ambiguous warning, never a
     hard error on an unknown code.
4. Rust (`bill_rules`): optionally mirror the check so the rules output is
   authoritative regardless of caller.
5. Tests on both sides + a demo input in `bill_rules/examples/demo.rs`.

### Acceptance criteria
- [ ] `place_of_service` present in both Rust and Python schemas.
- [ ] A POS↔CPT mismatch is flagged with a clear message and a stable rule_id.
- [ ] Unknown POS codes produce a low-severity warning, no false high flag.
- [ ] Existing Rust `#[test]` suite + Python validation tests still pass.

### Files to touch
- `bill_rules/src/types.rs`
- `data-extraction-service/app/models/parsed_bill.py` (already has the field)
- `data-extraction-service/app/services/validation_service.py`
- `bill_rules/src/rules/` (new module)
- `bill_rules/examples/demo.rs`, tests on both sides

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| False positives on real bills | Conservative rules keyed off CMS POS definitions; warnings ≤ depends |
| Rust schema drift vs Python | Add a cross-`ParsedBill`/`LineItem` contract test |

### First step (spike)
Add the Rust `place_of_service` field + a 3-row POS table, and one rule ("ED-only CPT
with non-ED POS") end-to-end before broadening.

---

## Ticket #13 — ICD ↔ CPT compatibility checks

- **Priority:** Medium · **Owner:** Rules (Python) ·
  **Depends on:** #11 (full CMS reference data for code presence).

### What it is
No code anywhere checks whether a bill's **diagnosis (ICD-10) codes are compatible
with its procedure (CPT/HCPCS) codes** (`ROADMAP.md:172-173`). The Rust engine only
runs duplicate/unbundling/reconciliation checks across CPT codes; the Python
validation services focus on per-code format/presence. ICD↔CPT compatibility is
unchecked.

### Goal
Add a **conservative** code-to-diagnosis compatibility pass that flags a clear
mismatch (e.g. a screening/diagnostic-only ICD paired with a screening-only
procedure in a way CMS treats as incompatible) without fabricating rules for
unknown combinations.

### Approach / scope
1. Define an explicit compatibility dataset/lookup (small & conservative at first):
   - a list of "procedure-only" vs "diagnosis-only" codes,
   - a curated set of known-incompatible ICD↔CPT pairs.
2. Implement the pass in `validation_service.py` (it already has `ref_data` +
   `line.icd10` and `line.cpt_hcpcs`).
3. Emit a stable rule_id (mirror the Rust `NCCI-*` style, e.g. `COMPAT-*`) with a
   severity (high for certain mismatches, medium/low otherwise).
4. Leave unknown codes unflagged (no false high).

### Acceptance criteria
- [ ] A known ICD↔CPT mismatch yields one flag (stable rule_id, clear message).
- [ ] Unknown/unlisted code combinations are never flagged.
- [ ] Tests cover a definite mismatch, a no-mismatch, and an unknown-code case.
- [ ] Rust `#[test]` suite unaffected (pure Python addition unless mirrored).

### Files to touch
- `data-extraction-service/app/services/validation_service.py`
- New: `data-extraction-service/app/services/compatibility.py` (dataset/loader)
- `data-extraction-service/tests/test_validation.py` (new cases)
- Reuse `reference_data.py` for code presence (#11)

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| High false-positive rate on real bills | Start with a tiny, curated, confirmed-incompatible set; conservative severity |
| ICD/CPT code expansion skew | Version the compatibility data with the CMS files (#11) |

### First step
Build the tiny confirmed-incompatible set (≈3–5 pairs/classes), wire one check in
`validation_service`, and prove it in a test before expanding.

---
---

## Ticket #14 — Data-driven NCCI loader (replace hardcoded pairs)

- **Priority:** Medium · **Owner:** Rules (Rust) · **Depends on:** none
  (data files can be added/reviewed independently).

### Current state
NCCI unbundling runs off **113 hardcoded pairs** baked into the binary:
`pub const NCCI_UNBUNDLING_PAIRS: &[(&str, &str)] = &[...]` at
`bill_rules/src/types.rs:105` (referenced by
`bill_rules/src/rules/unbundling.rs:32` and `engine.rs:40`). This is a tiny,
non-editable fraction of the real CMS NCCI edit set, so unbundling coverage is low
and adding/updating a pair requires a source recompile.

### Goal
NCCI edits are **data-driven**: loaded from an editable data file (JSON/TSV) or a
CMS NCCI edit set at runtime, so rules can grow without a rebuild and be audited.

### Approach / scope
1. Add a data file, e.g. `bill_rules/data/ncci_pairs.json` (or TSV) holding
   `(component, comprehensive)` pairs — migrate the existing 113 pairs into it.
2. Load it at startup into `AppState` (`bill_rules/src/main.rs` `AppState`, ~L26),
   replacing the compile-time constant in the rule.
3. Keep the rule logic (`detect_unbundling`) exact; only the data source becomes
   external.
4. Add a loader unit test + an integration test that the service flags on a loaded
   data file; keep the multi-component mapping tests.
5. (Optional) a `/reload` or watcher so data refreshes without restart.

### Acceptance criteria
- [ ] NCCI pairs load from a data file, not only from the compiled constant.
- [ ] The existing 113-pair behavior is preserved (no `#[test]` regressions).
- [ ] Adding an entry to the data file changes engine output without a recompile.
- [ ] Unknown/duplicate handling is conservative (no false high flags).

### Files to touch
- `bill_rules/src/types.rs`, `bill_rules/src/rules/unbundling.rs`
- `bill_rules/src/main.rs` (AppState, startup load)
- New: `bill_rules/data/ncci_pairs.json` + loader module
- `bill_rules/examples/demo.rs` / tests

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Missing data file at startup | Fail-loud; keep the 113 as an embedded seed/backup |
| Editing data without validation | Validate on load (pairs are 5-char codes) |
| Real NCCI set licensing | Start curated/editable; source CMS public data per #11 where allowed |

### First step (spike)
Extract the current 113 pairs into `ncci_pairs.json`, load it in `main.rs`, and
prove the existing tests pass with the loader — behavior identical, source of truth
now a file.

---
---

## Ticket #15 — Broader modifier appropriateness rules

- **Priority:** Medium · **Owner:** Rules (Python first, Rust optional) ·
  **Depends on:** #14 pattern (data-driven rules) for the broader set.

### What's already done
A basic modifier-appropriateness guard **landed recently** (commit `7c23bd9`):
- `validation_service.py:304-369` defines `_MODIFIER_REQ_EM` (`25`),
  `_MODIFIER_COMPONENT` (`26`/`TC`), and `_MODIFIER_SIDE` (`LT`/`RT`), with a
  conservative `_modifier_appropriateness_note()`.
- `_validate_modifiers` (`validation_service.py:371+`) runs reference lookups and
  flags misapplied modifiers.
- Covered by `tests/test_validation.py::TestModifierAppropriateness`
  (`test_component_modifier_on_imaging_is_allowed`,
  `test_modifier_25_on_non_em_code_is_flagged`, `test_side_modifier_on_em_code_is_flagged`, etc.).

### What remains (the "broader" rules)
The four curated modifier classes plus conservative unknown-handling are a start;
coverage is still narrow. Missing/unplanned areas include:
- Other high-signal modifiers: `GA`/`GZ` (advance beneficiary notice), `51`/`59`
  (multiple procedure / distinct service), `XE` (separate encounter), units/Bilateral
  cases.
- Broader CPT category routing (today's imaging detection uses description keyword
  matching, `validation_service.py:344-357`).
- Parity in the Rust engine so the deterministic output flags modifiers too.

### Goal
Expand the modifier guard in a **data-driven, conservative** way: more curated
modifiers/classes and better CPT routing, kept false-positive-low, optionally
mirrored in Rust.

### Approach / scope
1. Move the three curated classes into an editable table (extension of #14's data
   pattern) so rules grow without code churn.
2. Add 3–5 high-value modifiers with clear CPT targets; severity ≤ medium.
3. Improve CPT routing: add an explicit CPT-category list (radiology, E/M, surgery,
   laboratory) in `reference_data.py` to replace fragile keyword matching.
4. Decide scope of a Rust mirror (flag-consistency) and add conformance tests.
5. Unknown modifiers still resolve via `ref_data` lookup only; never a hard flag on
   an unlisted modifier.

### Acceptance criteria
- [ ] New modifiers flagged when misapplied, with a stable rule_id + message.
- [ ] CPT routing uses a category list, not only description keywords.
- [ ] Unknown modifier/CPT combos produce no false high flag.
- [ ] Existing `TestModifierAppropriateness` cases still pass (no regression).
- [ ] (If mirrored) Rust and Python emit consistent `MOD-*` flags.

### Files to touch
- `data-extraction-service/app/services/validation_service.py`
- `data-extraction-service/app/services/reference_data.py` (categorization)
- New: `data-extraction-service/app/services/modifier_rules.py` (or data table)
- `data-extraction-service/tests/test_validation.py`
- `bill_rules` (optional mirror) + tests

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Broader rules → false positives | Data-driven, conservative, severity ≤ medium; unknown = no flag |
| Keyword routing drifts | Move to reference-coded CPT categories in `reference_data` |

### First step
Port the current three curated tables to data, add one new modifier (e.g. `59`
distinct-procedure rules, with "must not be used with E/M or when global rules
disallow"), and keep tests green before expanding further.

---

## Rules Engine — dependency & sequencing note

```
#14 data-driven NCCI loader ──▶ (makes #15/#12 data-driven too)
#11 CMS reference data ──▶ #12 POS · #13 ICD↔CPT · #15 modifiers
```

Shared thread: **conservative and data-driven**. Every new rule should
(1) ship a test for a definite case, a no-case, and an unknown-code case, and
(2) never hard-fail on an unlisted code. The Rust engine guarantees determinism +
audit; the Python validation layer provides reference/appropriateness. Keep the two
sides consistent with conformance tests.