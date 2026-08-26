# Vitta — Reliability & Testing: Ticket Drafts

> Companion to `BACKLOG.md` (items #16–#18). Paste-ready drafts for a tracker.
> Line references are accurate as of 2026-08-26.

---

## Ticket #16 — Surface degraded mode clearly in UI + API

- **Priority:** Medium · **Owner:** Backend + Frontend · **Depends on:** none.

### Current state — a lot is already done
A degraded-mode disclosure already exists and works:
- **Frontend banner**: `frontend/app.js:1559` renders a "sample-data" banner when
  `extractionMode === "sample"`; `frontend/app.html:124` + `frontend/css/app.css:389`
  define it. The UI already refuses to pass synthesized figures off as the user's
  real bill.
- **Payload plumbing**: `frontend_adapter.py:500-502` emits `extractionMode`
  (`"sample" | "live" | None`), derived from the pipeline audit's `extraction_path`
  (`frontend_adapter.py:204-208`, `:460-462`).
- **Health**: `GET /health` returns `ok`/`degraded` with per-dependency reachability
  (`medical-bill-backend/app/api/routes/health.py:54-58`), covered by
  `tests/test_health.py`.

### What's still missing (the real gap)
The fallback is **not attributed with a reason**. In `extraction_client.py` every
degrade path *logs* why it happened but **returns the same mock** regardless:
- disabled (`:41-45`), missing text (`:55-60`), timeout (`:86-92`),
  unreachable (`:94-100`), HTTP error (`:102-109`), unexpected (`:111-115`).

So the response/UI can only say "sample," not *"extraction service unreachable, fell
back to heuristic"* vs *"rules engine disabled."* The same applies to the rules
engine client (`rules_engine.py:51-79`). A disabled service is still visually
indistinguishable from a broken one — you see "sample" either way.

### Goal
Every degraded result carries a **machine-readable reason** so operators and the UI
know *which* dependency degraded and *why*, and the UI renders the specific reason
next to the existing banner.

### Approach / scope
1. Make the fallback return a reason: have `extraction_client.extract_and_score()`
   and the rules-engine client produce a structured result
   `(bill, degraded_reason: None | "extraction_disabled" | "extraction_timeout" |
   "extraction_unreachable" | "extraction_error" | "rules_disabled" |
   "rules_unreachable" | "llm_fallback")`.
2. Thread the reason into the pipeline `audit` (`pipeline.py:210+` already builds one)
   and set it on the API response.
3. Surface it in the response payload (e.g. `degraded: {reason, dependency}`) and
   have `frontend_adapter.py` map it into the banner text (not just `extractionMode`).
4. Add a test: disable the extraction service and assert the response carries the
   `extraction_disabled` reason and the UI banner shows it.

### Acceptance criteria
- [ ] A disabled/broken service produces a distinct, machine-readable `degraded`
      reason (not just `"sample"`).
- [ ] The frontend banner includes the reason (e.g. "extraction service down —
      showing sample data").
- [ ] `/health` already aggregated — extend test coverage to the new field.
- [ ] A `tests/` case asserts the reason for each fallback path.

### Files to touch
- `medical-bill-backend/app/services/extraction_client.py`
- `medical-bill-backend/app/services/rules_engine.py`
- `medical-bill-backend/app/services/pipeline.py` (audit)
- `medical-bill-backend/app/services/frontend_adapter.py`
- `frontend/js/app.js`, `frontend/app.html` (banner text)
- `tests/test_frontend_adapter.py`, `tests/test_health.py`

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Over-engineering the reason taxonomy | Start with a small enum (above) and grow only as needed |
| Reason leaks PHI | Reasons are static enum strings, never bill content |

### First step (spike)
Add the `degraded` reason to the `extraction_client`'s mock return contract with a
test for the disabled path; then thread it into `audit`/response.
---

## Ticket #17 — Real document fixture corpus (PDFs, images)

- **Priority:** High (the "free win") · **Owner:** Data/ML + Ops ·
  **Depends on:** none (parallelizable) · **Feeds:** #1 (OCR), #8 (annotation),
  #18 (LLM tests), and e2e tests.

### Current state
There are **no PDF/PNG/JPG fixtures anywhere in the repo** — every test input is a
synthetic Python string literal (`ROADMAP.md:188-193`). The e2e smoke test
(`medical-bill-backend/scripts/e2e_smoke_test.py`) uploads a **27-byte fake PDF**.
Consequently: OCR (#1) has nothing realistic to run against, the LLM extraction path
(#18) has no real input, feature/models tests (#7–#10) can't consume real evidence,
and the "does it look right end-to-end" question can't be answered.

### Goal
A small, **fully de-identified** corpus of real bills/EOBs with per-fixture gold
JSON, committed under `fixtures/` and consumed by tests across all services.

### Approach / scope
1. Collect a minimal corpus by format: ≥1 text-layer PDF, ≥1 scanned PDF, ≥1 PNG,
   ≥1 JPEG, ≥1 EOB (add a WEBP if possible).
2. **De-identify** before committing: names, DOB, SSN/MRN, addresses, insurer IDs,
   and any PHI in filenames or embedded metadata. Run a redaction check.
3. Produce a **gold JSON** per fixture mirroring the `ParsedBill` contract
   (codes, amounts, totals, provider/payer, expected flags) plus an optional
   "known issues" list for rules-engine tests.
4. Add `fixtures/MANIFEST.md` (source origin, de-id status, license, date) and a
   loader/validator helper (`fixtures/gold/`).
5. Convert the highest-value tests to run against the corpus (start with ingestion +
   heuristic extraction + rules), keeping the existing string-literal tests.

### Acceptance criteria
- [ ] ≥1 fixture per format (text PDF, scanned PDF, PNG, JPG, EOB).
- [ ] Every fixture has a gold JSON validated against the `ParsedBill` schema.
- [ ] De-identification checked; no PHI in filenames, source text, or metadata.
- [ ] Ingest/extraction/rules tests can load a fixture by helper and pass.
- [ ] The 27-byte fake-PDF smoke test is replaced by a real fixture.

### Files to touch
- New: `fixtures/` (+ `fixtures/gold/*.json`, `fixtures/MANIFEST.md`)
- New: `fixtures/load.py` (or `tests/fixture_loader.py`) — shared fixture reader
- `data-extraction-service/tests/`, `medical-bill-backend/tests/`
- `medical-bill-backend/scripts/e2e_smoke_test.py`

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| PHI leak via OCR text/metadata | De-id first + redaction check; never commit raw source |
| Fixture set too small to generalize | Frame as *fixtures for tests*, not a final training set (#8) |
| Gold-label drift vs schema | Validate gold JSON against `ParsedBill` on load |

### First step (spike)
Commit 2–3 de-identified documents (one text PDF, one PNG, one EOB) with hand-written
gold JSON, add the loader helper, and convert the ingestion test to read them.
---

## Ticket #18 — Tests & mocks for the LLM extraction path

- **Priority:** Medium · **Owner:** Extraction · **Depends on:** none
  (a #17 fixture is helpful but not blocking).

### Current state
The **LLM extraction path has zero direct tests and zero mocks**. `ExtractionService`
selects the path in `extract()` (`extractor.py:176-179`):
- LLM: `_extract_with_llm` (`extractor.py:333-400`)
- fallback: `_extract_heuristic` (`extractor.py:421+`)

Existing tests only exercise the heuristic path by forcing `llm_configured=False`
(`tests/test_extraction.py:14-17`), and the LLM branch is marked
`# pragma: no cover` at the failure point (`extractor.py:390`). The instructor call
(`self.instructor_client.chat.completions.create(... response_model=PB ...)`,
`extractor.py:377-383`) — schema-constrained output, provenance, warning merging, and
the `LLM_FAILURE` → heuristic fallback (`:390-399`) — is untested.

### Goal
The schema-constrained LLM path is covered by tests that **mock the instructor
client** (no network), asserting:
1. It returns a valid `ParsedBill` (schema conformance).
2. Provenance/confidence from tokens is preserved into the output.
3. Pre-flagged OCR warnings are merged into the LLM result (`:384-388`).
4. On an exception it falls back to the heuristic parser with an `LLM_FAILURE`
   warning (`:390-399`).

### Approach / scope
1. Add a fake `instructor_client` to `tests/` that returns a canned `ParsedBill`
   (or raises) without any network.
2. Test 1 — happy path: set `svc.llm_configured = True`, swap
   `svc.instructor_client` for the fake, call `extract()`, assert a `ParsedBill`
   with the expected codes/amounts and merged warnings.
3. Test 2 — provenance: assert per-field `provenance`/`ocr_confidence` survive.
4. Test 3 — warning merge: pre-flagged `warnings` appear in the result.
5. Test 4 — failure fallback: fake raises; assert the result is the heuristic bill
   and an `LLM_FAILURE` high-severity warning is present.
6. Remove the `# pragma: no cover` on the failure branch and re-enable coverage.

### Acceptance criteria
- [ ] Mocked-client tests cover the LLM happy path, provenance, warning merge, and
      failure fallback.
- [ ] No network access in these tests (pure mock).
- [ ] The `LLM_FAILURE → heuristic` branch is covered (drop the `no cover`).
- [ ] `tests/test_extraction.py` + new `tests/test_llm_extraction.py` all pass.

### Files to touch
- New: `data-extraction-service/tests/test_llm_extraction.py` (+ a `FakeInstructor` helper)
- `data-extraction-service/app/services/extractor.py` (remove `no cover` marker)
- Optionally consume a #17 fixture for the input text

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Mock drifts from real instructor API | Keep the fake narrow (only the calls `_extract_with_llm` uses); document it |
| Coverage gate complains | Drop the `no cover`; these tests are the point |

### First step
Write the fake client + the failure-fallback test first (highest value: it proves
the honest degradation), then the happy path + provenance + warning-merge tests.

---

## Reliability & Testing — dependency & sequencing note

```
#17 fixtures ──▶ #1 OCR validation (real inputs)
        └──────▶ #18 LLM tests (real-ish input) + e2e
#16 degraded reason ──▶ honest UI/API (independent, parallel)

```

The thread across all three: **honesty and realism**. #16 makes degraded behavior
*visible*; #17 makes tests *real*; #18 makes the untested LLM branch *provable*.
#17 is the keystone — it unblocks #1, #18, and feeds #8/#9.