# Vitta — Data & Models: Ticket Drafts

> Companion to `BACKLOG.md` (items #7–#11). Paste-ready drafts for a tracker,
> with acceptance criteria, file touch-lists, risks, and a first spike step.
> Line references are accurate as of 2026-08-26.

---

## Ticket #7 — Real CMS / fair-price benchmarks

- **Priority:** High (real-data) · **Owner:** Data/ML ·
  **Depends on:** #11 (full CMS data) · **Unblocks:** #9 (retrain).

### Problem
The pricing model's anchor feature, `fair_price`, comes from a handpicked
**~33-code synthetic table**: `CPT_FAIR_PRICE` at
`data-extraction-service/app/ml/synthetic_data.py:44-78`, with a flat **$100
fallback** for any unknown code. Geographies/provider types/payers are likewise
synthetic lists (`synthetic_data.py:80-91`). A charge is judged "anomalous"
relative to these invented dollars — not real CMS pricing. So the pricing-anomaly
flag and any SHAP explanations built on it are not yet grounded in reality.

### Goal
`fair_price` (and the charge-to-fair-price ratio) is computed from **real CMS
pricing benchmarks** (e.g. CMS fee schedules / Medicare physician fee schedule), per
CPT, geography, and provider type where available, with a documented fallback —
never a silent synthetic constant.

### Approach / scope
1. Source a real CMS benchmark (Medicare Physician Fee Schedule national/local
   amount files, or an open fair-pricing dataset). Legal/licensing check first.
2. Replace `CPT_FAIR_PRICE` with a loader over that dataset, keyed by
   `(CPT/HCPCS, geography, provider_type)` where the data supports it.
3. Define an explicit fallback policy for codes absent from CMS data (document the
   fallback value/behavior — a silent flat $100 is not acceptable).
4. Keep `synthetic_data.py` generation for tests, but clearly label train vs
   production feature paths so retrained models consume real benchmarks.
5. Update `tests/test_ml.py` / `tests/test_feature_stability.py`
   (`test_fair_price_feature_is_process_independent`) to use the new source.

### Acceptance criteria
- [ ] `fair_price` is derived from a real CMS benchmark, not a synthetic constant.
- [ ] Unknown codes follow a documented fallback (logged, not silent).
- [ ] The feature pipeline for real bills uses the real path; synthetic path is
      test-only and labelled.
- [ ] Feature-stability tests pass (deterministic across processes — see #10).

### Files to touch
- `data-extraction-service/app/ml/synthetic_data.py`
- `data-extraction-service/app/services/scoring_service.py`
- New: `data-extraction-service/app/services/pricing.py` (or a loader in
  `reference_data.py`)
- `data-extraction-service/app/config.py`, `data-extraction-service/tests/*`

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Licensing of CMS fee files | Use public/free datasets; record source + date |
| Geography granularity gaps | Document fallback hierarchy (state → national → default) |
| Real prices shift the anomaly distribution | Version the benchmark (data date stamped with the model) |

### First step (spike)
Fetch and inspect one CMS fee-schedule file, confirm the columns allow a
CPT × geography lookup, and prototype loading 3 known codes to sanity-check fair
vs. real values.

---

## Ticket #8 — Collect & annotate real de-identified medical bills

- **Priority:** P · **Owner:** Data/ML + Ops · **Depends on:** #17 (fixtures) ·
  **Unblocks:** #9 (retrain).

### Problem
There is **no real bill data anywhere in the repo** — every test and training
input is a synthetic string literal, and there is not a single PDF/PNG/JPG fixture
(`ROADMAP.md:188-193`). Models are fit on a synthetic distribution; real accuracy is
unknown. Collecting labeled real bills is the single highest-value data asset.

### Goal
A curated, **fully de-identified** corpus of real medical bills/EOBs with a
**gold-annotated JSON** per document (codes, amounts, denials, flags, appeal
outcome where known) that powers validation, fixture tests, and retraining.

### Approach / scope
1. Gather real bills (de-identified public EOBs, patient/sample donations,
   or realistic surrogates — disclosed clearly if synthetic).
2. De-identify (names, DOB, SSN/MRN, addresses, insurer-specific IDs).
3. Build a gold JSON format + manifest mirroring the `ParsedBill` schema.
4. Version the corpus and an annotation checklist so labels are auditable.
5. Feed #17 (fixture corpus) from this — one pipeline, two consumers.

### Acceptance criteria
- [ ] ≥ the P0 fixture minimum: a text PDF, a scanned PDF, a PNG, a JPG, an EOB.
- [ ] Every fixture has a gold JSON validated against the `ParsedBill` schema.
- [ ] De-identification checked (no PHI in filenames/source text).
- [ ] Label provenance/annotator recorded (auditable).

### Files to touch
- New: `fixtures/` (+ `fixtures/gold/*.json`, `fixtures/MANIFEST.md`)
- `data-extraction-service/tests/` (fixture-driven tests)
- `data-extraction-service/app/services/annotation.py` (annotation validator)

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| PHI leaks during collection | De-identify first, PHI-scrub check, never commit raw docs |
| Small corpus → overfit | Treat metrics as *empirical*, not *final* |
| Label noise | Two-pass annotation or documented single-annotator policy |

### First step (spike)
Collect 2–3 de-identified PDFs/images, hand-produce one gold JSON, and wire the
parser to ingest it — proves the format before mass collection.
---

## Ticket #9 — Retrain pricing & appeal models on real data

- **Priority:** P · **Owner:** Data/ML · **Depends on:** #8, #7, #10.

### Problem
The reported **0.97 accuracy / 0.98 AUC** in `models/pricing_anomaly_metrics.json`
is a train/test split of **one synthetic distribution whose labels were produced by
explicit rules** — it is not real performance and should not be quoted as such
(`ROADMAP.md:151`). Retraining on real labels is the only way to get honest numbers.

### Goal
The pricing-anomaly and appeal-success models are (re)trained on the real corpus
(#8), consuming real features (#7, #10), and their metrics are recomputed and
clearly labelled as real-data performance.

### Approach / scope
1. Split the real corpus (train/val/test) with a documented seed.
2. Switch the settings to use real features (disable the synthetic path) and re-train.
3. Recompute metrics and ship a new, **dated** `models/pricing_anomaly_metrics.json`.
4. Add a CI gate that re-runs eval on the held-out set so regressions are caught;
   keep synthetic tests separate.

### Acceptance criteria
- [ ] Models retrained on real labels; metrics JSON updated, dated, source-tagged.
- [ ] Held-out eval is deterministic and re-run in CI.
- [ ] The old synthetic 0.97/0.98 is not presented as real performance anywhere.

### Files to touch
- `data-extraction-service/app/ml/models.py`
- `models/pricing_anomaly_metrics.json`, `models/*`
- `data-extraction-service/tests/test_ml.py`
- README metrics caveat

### First step
Run an eval on the real corpus with the *current* model first — capture a baseline
true accuracy before retraining so you can show the delta.

---

## Ticket #10 — Finish deriving all scoring features from the actual bill

- **Priority:** High · **Owner:** Data/ML · **Depends on:** #7 ·
  **Coupled with:** #8, #9.

### What's done
Geography, provider-type, and payer are now **derived from the bill** rather than
hardcoded (`scoring_service.py`, `tests/test_feature_derivation.py`:
`place_of_service` → provider type, provider state → geography, real payer name →
canonical category). These were the "constant features" gap — now closed.

### What remains
`fair_price`/`charge_ratio` still come from the synthetic benchmark (#7), and some
helper derivations in `synthetic_data.py` remain synthetic placeholders. Models
trained on invented features cannot generalize (`ROADMAP.md:143-149`).

### Goal
Every feature a model consumes is derived from the actual bill + real reference
data, with no hidden synthetic constants, and the pipeline is deterministic across
processes (stable-features test).

### Acceptance criteria
- [ ] No scoring feature in a production path uses a synthetic constant as truth.
- [ ] Any unresolved/unavailable feature has an explicit, logged fallback.
- [ ] `tests/test_feature_stability.py` (deterministic across processes) passes.

### First step
Inventory the model's feature set (`models.py:54-75`: `charge_amount`,
`allowed_amount`, `fair_price`, `charge_ratio`, `prov_type_code`, `geo_code`,
`payer_code`) and mark each: derived-from-bill / real-reference / synthetic. Any
synthetic one becomes a blocker.
---

## Ticket #11 — Full CMS ICD-10 / CPT reference data loading (status: loader FIXED)

- **Priority:** High · **Owner:** Data/ML · **Depends on:** data assets.

> **Status note:** The **code-level bug has already been fixed** (landed after the
> ROADMAP audit). `_load_cms_csv` now routes single-category files correctly and
> fails loudly on a zero-row load — `reference_data.py:212-265` — covered by
> `tests/test_reference_cms_loading.py` (icd10 letter-codes, cpt/hcpcs split, alpha
> modifiers, deprecated flags). What remains is **data + validation**, not more code
> surgery.

### What's left
The repo still carries a **bundled proxy dataset** (`_load_bundle`) and expects the
real CMS files to be mounted at `REFERENCE_DATA_DIR` (`config.py:35`,
`docker-compose.yml:44` → `/app/data/reference`). That directory ships with only a
proxy/partial dataset. Full CMS `cpt_hcpcs.csv`, `icd10.csv`, `modifiers.csv` are
not tested end-to-end.

### Goal
Real, versioned CMS reference files load cleanly, are validated (row counts,
required columns, status semantics), and are used by validation — in development and
in the `docker-compose` deployment.

### Approach / scope
1. Bundle (or download at CI time) the full CMS files with a pinned version date.
2. Add a loader test using the **full** files (not just the proxy bundle) inside
   `tests/test_reference_cms_loading.py`.
3. Add a `validate()` step on load: assert non-zero rows per category and required
   columns present; surface the outcome in `/health`.
4. Verify the `docker-compose` volume (`REFERENCE_DATA_DIR`) wires the real files.

### Acceptance criteria
- [ ] Full CMS files load with expected row-count validation (fail loudly if not).
- [ ] Validation uses the full reference set for CPT / HCPCS / ICD-10 / modifiers.
- [ ] `docker compose up` serves the real dataset (volume mounted), not proxy only.
- [ ] Tests assert non-empty load for each code type.

### Files to touch
- `data-extraction-service/app/services/reference_data.py` (validation additions)
- `data-extraction-service/app/config.py`
- `docker-compose.yml`, the `data/reference/` volume contents
- `data-extraction-service/tests/test_reference_cms_loading.py`

### First step
Download the real CMS ICD-10 + CPT files, mount them, run
`tests/test_reference_cms_loading.py`, and fix anything the loader still trips on
before closing this ticket.

---

## Quick dependency chain (Data & Models)

```
#11 (real reference data) ──▶ #7 (real benchmarks) ─┐
#8  (annotate real bills) ──▶ #10 (real features) ──┼──▶ #9 (retrain + baseline)
                                                   │
#17 (fixtures, from #8) ──▶ OCR validation (#1) ────┘
```

Bottom line: **#8 is the keystone** — it feeds the fixture corpus (#17), which in
turn validates OCR (#1), the rules-vs-ML split, and gives #9 honest training data.