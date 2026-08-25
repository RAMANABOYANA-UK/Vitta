# vitta — Engineering Roadmap

Grounded in a code audit of `data-extraction-service`, `medical-bill-backend`, `bill_rules`, and the static
frontend, conducted 2026-08-23. Every claim below cites the file and line that supports it. Where this
document contradicts an earlier assessment, the contradiction is deliberate and the evidence is given.

---

## 0. Corrections to the previous assessment

Read this section before planning around the older write-up. Five of its claims were wrong, and four of
them were wrong in the optimistic direction.

**"OCR quality depends on the provider (local tesseract is basic)."** There is no OCR in this codebase.
A repo-wide search for tesseract, pytesseract, Textract, Document AI, Form Recognizer, paddle, easyocr,
pdf2image, pypdf, PyMuPDF and pdfplumber returns only two explanatory *comments* in
`data-extraction-service/app/services/extractor.py` (L138, L226). `requirements.txt` contains no OCR or PDF
dependency, and `config.py` has no OCR provider setting. `raw_ocr_text` and `layout_json` are **inputs** to
the service (`app/main.py` L53-57) — something upstream is expected to have already produced them, and
nothing in the repo does. This is not a quality problem to tune; it is a missing front door.

**"Auth is simple (static token + basic JWT)."** There is no authentication of any kind. `app/core/security.py`
is 29 lines containing three helpers, and its own docstring says authorization "will be layered in a later
phase" (L4-5). There is no user model, no password hashing, no tenant or owner column — the only table is
`Document` (`app/models.py` L11-34). All five document endpoints depend on nothing but a DB session
(`app/api/routes/documents.py`), so **any caller can read or patch any document by ID**, and CORS is
`allow_origins=["*"]` with `allow_credentials=True` in development (`app/main.py` L64-70). For a system that
will hold PHI, this is the single most serious finding in the audit.

**"Frontend has mock mode but real integration assumes the backend is running with the correct token."**
Real mode cannot work at all, token or not. The frontend calls nine endpoints — `POST /upload`,
`GET /jobs/{id}/status`, `WS /ws/jobs/{id}`, `GET /bills/{id}`, `GET /bills/{id}/flags`,
`GET /bills/{id}/appeal-score`, `POST /bills/{id}/appeal-score/recompute`, `GET /codes/{code}`,
`GET /codes?q=` (`js/api.js` L7-15, L1092-1273) — and the backend serves none of them; its router is
mounted at `/api/v1/documents` (`app/api/routes/documents.py` L37). Separately, `js/app.js` L15 calls
`VittaAPI.create()` with no arguments, so `authToken` is `null` and the `Authorization` header is never
sent; there is no UI or config to supply one, and the base URL is a relative `/api/v1` (`js/api.js` L718).

**"Better visualization of flags, SHAP explanations, provenance, and audit trail" is needed.** This is
already the strongest part of the product. The UI renders flag cards with severity, category, dollar impact,
confidence and a rule-vs-ML badge (`js/app.js` L1099-1160), a labelled SHAP contribution panel
(L1099-1110), bounding-box provenance overlaid on the page image (L934-1050), per-field verification badges
with confidence tooltips (L806-818), and an appeal score with confidence interval and factor breakdown
(L1214-1300). What is actually missing is narrower and more important: the appeal letter shown to the user
is generated **client-side from a JavaScript template literal** (`js/app.js` L1354-1406), which means it
never touches the backend's grounded-and-verified letter path. The audit "timeline" is a hardcoded 5-step
template, not real events (L1571-1597).

**"Dockerfiles are limited."** There are zero Dockerfiles. The only container asset in the repo is
`medical-bill-backend/docker-compose.yml`, a single `postgres:16-alpine` service with the password
hardcoded to `password` (L10).

Two claims were understated in the other direction, and deserve credit. The **Rust rules engine is real and
genuinely good**: an Axum HTTP service on port 3001 (`bill_rules/src/main.rs` L53-63) running reconciliation,
duplicate and unbundling passes deterministically (`engine.rs` L16-40) over 113 hardcoded NCCI pairs
(`types.rs` L105-250), covered by 32 `#[test]` functions. And the **letter verifier is a real
mechanism, not a gesture**: six checks against the source bill covering claim number, service date in four
formats, labelled and unlabelled procedure codes, NPI, denial codes and every dollar figure
(`letter_verifier.py` L47-217), with generation forced to label codes and to fall back to a template on
failure (`letter_generator.py` L20-46).

One further correction worth noting: the audit found no secrets committed. Only `.env.example` files are
tracked; `medical-bill-backend/.env` exists on disk but is correctly gitignored.

---

## P0 — Correctness bugs that silently invalidate current output

These come before every item in the previous roadmap. Each is small, each is confirmed, and together they
mean the system's current outputs cannot be trusted even on synthetic data. Fixing them is a matter of days.

| # | Location | Symptom | Fix |
|---|---|---|---|
| 1 | `data-extraction-service/app/db.py` L132-133 | Reads `totals.allowed_total` and `totals.paid_total`, which are not defined — `parsed_bill.py` only declares `billed_total` (L268) and `patient_responsibility_total` (L276). Raises `AttributeError` outside the try block, so `/validate`, `/score` and `/pipeline` all return HTTP 500 **whenever `DATABASE_URL` is set**. Invisible today only because `app/db.py` has no test file. | Add the missing properties or stop persisting those two fields. Add a persistence test. |
| 2 | `app/ml/synthetic_data.py` L86, L203-204 | Feature values derive from Python's `hash()` on strings, which is randomized per process. Verified empirically: the same input returned 486, 501 and 646 across three fresh interpreters. **A persisted model is therefore served features drawn from a different distribution than it was trained on**, and `settings.synthetic_seed` does not fix it. | Replace with a stable digest (e.g. `hashlib.blake2b`) or an explicit lookup table. Add a cross-process feature-stability test. |
| 3 | `medical-bill-backend/app/services/pipeline.py` L179 | `verification_passed = len(verified) > 0` — reports success from the *count of verified fields* and never consults the problems list. A letter carrying verified fields **and** unresolved problems is still recorded as passed. (The template-fallback path is separately re-verified and does pass cleanly, so the real exposure is a partially-verified genuine letter, not the fallback.) | Set from `problems == []`. This is safety-critical and belongs in the same commit as a regression test. |
| 4 | `app/services/reference_data.py` L207-209, L235-236 | `_load_cms_csv` routes on `code[0].isalpha()` but is passed `None` for the ICD-10 and modifier alpha maps, then silently skips. Since every ICD-10 code begins with a letter, **dropping in a full CMS `icd10.csv` loads zero codes**, with no warning. Alpha modifiers (`LT`, `RT`, `GA`) are dropped too. | Fix the routing, and make a zero-row load a loud error rather than a silent one. |

Two pieces of dead weight to clear at the same time: `medical-bill-backend/verify_bridge.py` calls three
functions that no longer exist in `rules_engine.py` and dies with `AttributeError` on L34, and
`medical-bill-backend/import_check.txt` is a committed 48-byte UTF-16 build artifact.

---

## P1 — Make one real bill work end to end

The pipeline architecture is sound, but as configured and wired it cannot process a real document. Three
things stand between the current state and "a PDF goes in, a verified letter comes out."

**Build the ingestion layer that does not exist.** Because `raw_ocr_text` and `layout_json` are inputs, some
component has to produce them. This is the largest genuinely missing piece of the system and it gates all
real-bill work, including data collection. The service already emits `MULTIPAGE_TABLE` and
`HANDWRITING_DETECTED` warnings (`extractor.py` L212-235) and carries bounding-box provenance through to the
frontend overlay, so the contract to build against is already defined — start with one provider behind an
interface rather than trying to be provider-agnostic on day one.

**Reconcile the frontend and backend API contracts.** Nine expected paths, zero matching. Decide which side
moves — the frontend's resource-oriented shape (`/bills/{id}`, `/jobs/{id}/status`) is the better long-term
design than `/api/v1/documents`, but the backend is where the logic lives. Note that the frontend expects
flags and appeal score to arrive embedded in the job-status payload, since `getFlags` and `getAppealScore`
are defined but never called (0 call sites in `js/app.js`). Then plumb a token and a configurable base URL
through `VittaAPI.create()`.

**Route letter generation through the verified backend path.** The client-side template at `js/app.js`
L1354-1406 bypasses `letter_verifier.py` entirely, which means the safety mechanism the system was designed
around does not protect the artifact the user actually sends to an insurer. Until this is fixed, the
verifier's quality is irrelevant in practice.

Worth noting the enablement flags, because they change what "out of the box" means. A fresh clone's
committed defaults (`config.py`; `.env.example` L30, L37, L42) have the **rules engine and LLM on** but the
**extraction service off** — so it runs mock-extracted bills through the real Rust rules engine and a real
LLM-generated, verified letter. The gitignored local `.env` on the current machine sets all three to false,
which is why the pipeline behaves *here* as mock input, no rules, template letter — but that is a local
condition, not the shipped default. Every service failure path also falls back to
mock or un-enriched data (`extraction_client.py` L78-109, `rules_engine.py` L51-79). Graceful degradation is
a real strength here, but combined with the local override it currently makes a disabled or broken
configuration indistinguishable from a working one — surface the degraded mode in the response payload and
in the UI.

---

## P2 — The PHI gate

This is a hard prerequisite, not a priority to be traded off. No real patient bill should touch this system
until there is authentication, per-user data scoping, and an owner column on `Document`. The current state
is that any caller can read or patch any document by ID. Handling real medical bills without this is a
disclosure incident waiting for its first user, and it is also the thing most likely to be
uncomfortable to explain retroactively.

Scope for a first pass: a user model with hashed passwords, real session or token issuance to replace the
`login.html` placeholder that writes a hardcoded user to `localStorage` (L387-417), an `owner_id` on
`Document` with every query scoped to it, expiry on tokens, a CORS allowlist, and rate limiting on upload.
Structured audit logging of who accessed which document belongs here too — it is both a compliance need and
the real data behind the frontend's currently-hardcoded timeline.

---

## P3 — Real data and model quality

This was the previous roadmap's top priority. It should move behind P0 and the ingestion work, because the
sequencing matters: **retraining on real bills before fixing the feature pipeline would waste the
annotation effort.** Three of the eight scoring features are hardcoded constants — geography is always
`"NY"`, provider type always `"primary_care"`, payer always `"payer_a"`
(`app/services/scoring_service.py` L229-244) — and `fair_price` comes from a 33-code synthetic benchmark
table with a flat $100 fallback for unknown codes (`synthetic_data.py` L106), not from CMS pricing. A model
retrained on real labels while still consuming invented features cannot generalize.

So the order is: fix the `hash()` nondeterminism (P0 #2), derive the three constant features from the bill,
replace the synthetic fair-price table with real CMS pricing, and only then collect and annotate real bills
and retrain. Note also that the reported 0.97 accuracy and 0.98 AUC in `models/pricing_anomaly_metrics.json`
are a train/test split of one synthetic distribution whose labels were generated by explicit rules
(`synthetic_data.py` L155-179), so the model is substantially re-learning a known formula. Those numbers
should not be quoted as evidence of real-claim performance anywhere, least of all to a clinical or investor
audience. The calibration and SHAP infrastructure around them is real and worth keeping
(`models.py` L199-207).

One caveat on expanding reference data: the ICD-10 CSV loader is broken (P0 #4), so "drop in the full CMS
files" does not currently work regardless of which files you obtain.

---

## P4 — Rules engine expansion

The best accuracy-per-hour available without any real training data, because deterministic rules need no
labels and produce explanations a patient and an insurer can both follow. The engine is already structured
for it and well tested.

Two clear gaps. **Modifier validation** does not exist — the `modifiers` field is declared at
`bill_rules/src/types.rs` L34 and never read by any rule, and while the Python side checks modifier *format*
(`validation_service.py` L249-291) nothing checks appropriateness. **Place-of-service validation** cannot be
built yet, because `place_of_service` is absent from both the Rust and Python schemas; that is a schema
change first. Beyond those, the 113 hardcoded NCCI pairs are a small fraction of the real edit set and want
a data-driven loader, and code-to-diagnosis compatibility is unchecked. Worth fixing while in here: the
three-way totals check in `validation_service.py` L397-398 reduces algebraically to a two-way check, and the
extracted `adjustments_total` is never used.

---

## P5 — Production readiness, frontend polish, ops

Deferred deliberately: there is no value in a Kubernetes manifest for a pipeline that cannot yet read a PDF.
When this becomes the priority, the starting point is a Dockerfile for each of the four services, since none
exist; the compose file covers only Postgres and hardcodes its password. Secrets management, monitoring, and
CI/CD follow. Also queue the durability gap at `documents.py` L123, where processing is a fire-and-forget
`asyncio.create_task` with no queue and no persistence across restart, so an interrupted process leaves
documents stuck in `processing` with only the manual `/reprocess` endpoint as a remedy.

Test coverage is thinner than the counts suggest. There are 33 passing tests in the extraction service, 12
in the backend and about 29 in Rust, but **every input is a synthetic Python string literal — there is not a
single PDF, PNG or JPG anywhere in the repository**. The LLM extraction path has zero tests and zero mocks,
`app/db.py` has no test file at all (which is why P0 #1 survived), the CMS CSV loader is untested (P0 #4),
and `scripts/e2e_smoke_test.py` requires running services and uploads a 27-byte fake PDF. A fixture corpus
of real de-identified bills is the highest-value test asset to build, and it comes free with the P3
annotation work.

On accessibility, the audit found specifics worth fixing rather than a vague need for polish: there is no
`:focus` or `:focus-visible` rule in either stylesheet, so keyboard focus is browser-default only; the nav
collapses to a 72px icon rail at ≤1024px where `.nav-label` is hidden (`css/app.css` L1369) and the buttons
have no `aria-label`, so all nine navigation controls lose their accessible name; the sidebar is never
hidden at ≤640px and there is no hamburger in `app.html`; only 3 `for=` attributes exist across both forms
against 17 controls; `app.html` has eight `<h1>` elements and one `<h2>`; `login.html` has no landmarks and
no ARIA at all; and `#cbd5e1` is used as text on white at roughly 1.5:1 contrast, well below the 4.5:1
threshold.

---

## Suggested sequencing

Fix P0 first — days of work, and until it is done every output including the demo is untrustworthy. Then
P1 in parallel with starting P2, since ingestion is the long pole and auth is the gate on real data. P3
begins with feature repair, not data collection. P4 is the best use of any spare capacity throughout,
because it improves real accuracy without depending on anything else. P5 when there is something worth
deploying.

The architecture is not the problem here. The layered design, the deterministic-rules-plus-ML split, the
provenance tracking and the letter verifier are all well-judged choices for a high-stakes domain, and the
graceful degradation is a genuine strength. The gap is that several load-bearing pieces are wired to
constants, mocks or bugs in ways that are invisible without reading the code — which is precisely why the
previous assessment read more favourably than the codebase warrants.

---

## Unresolved question worth a decision

The letter verifier checks codes, dates, NPIs, denial codes and dollar amounts against the source bill, but
it does **not** check regulatory or statutory citations, and it cannot detect a real number used in the
wrong context (acknowledged in `letter_verifier.py` L187-195). For a product whose output is a letter sent
to an insurer, a fabricated statute or appeal-deadline citation is the highest-liability failure mode in the
system and it is currently unguarded. Options are to constrain letters to a fixed library of pre-approved
citation strings, to verify citations against a reference corpus, or to omit citations entirely from
generated text. This needs a decision before any letter reaches a real payer.
