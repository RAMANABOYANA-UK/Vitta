# Vitta — Engineering Backlog

> Status snapshot: **2026-08-26** — canonical list, renumbered to the final
> consolidated set. Recent commits already landed modifier guards, Dockerfiles,
> auth/ownership tests, PDF text extraction, billing-derived scoring features, the
> citation guard, and letter download/email endpoints, so those are excluded.
>
> Every item carries **file:line evidence** for its current state so it can be
> degraded into a ticket without re-auditing. Line references reflect the repo on
> this date and may drift.
>
> **Legend** — `[ ]` open · `[~]` in progress · `[x]` done (tick them off as work
> lands).

---

## Critical — (blocks real patient bills · next 2 weeks)

### `[ ]` #1 — Functional OCR for images & scanned PDFs
- **Current state:** Images and scanned/text-less PDFs are gated behind
  `OCR_ENABLED` (`config.py:60`, `docker-compose.yml:65`) and currently **fail
  honestly**: `scanned_pdf_needs_ocr` (`ingestion.py:249`) and `ocr_not_configured`
  (`ingestion.py:267`). `pytesseract`/tesseract is imported lazily, not installed
  (`requirements.txt:14-16`).
- **Scope:** Pick & configure a provider — local Tesseract binary, AWS Textract, or
  GCP Document AI. Rasterize scanned PDF pages before OCR (PyMuPDF), wire it, and
  plumb results through `method == "ocr"`.
- **Files:** `medical-bill-backend/app/services/ingestion.py`,
  `app/services/document_text.py`, `app/config.py`, `requirements.txt`,
  `docker-compose.yml`.
- **Acceptance:** real image + scanned-PDF uploads extract text successfully; the
  "OCR not configured" honest-error tests (`tests/test_ingestion.py`) exercise the
  real path; provider confidence/provenance is propagated.

### `[ ]` #2 — Real SMTP / transactional email sending
- **Current state:** The sender is a deliberate dev-safe "log instead of send"
  boundary (`app/services/mailer.py:1-6,36,43,58`). No SMTP/transactional provider
  is wired.
- **Scope:** Connect a transactional provider (SendGrid / SES / SMTP) with
  PHI-safe transport config, used for both verification and appeal-letter emails.
- **Files:** `medical-bill-backend/app/services/mailer.py`, `app/config.py`,
  `app/api/routes/auth.py`, `docker-compose.yml`, `.env.example`.
- **Acceptance:** a real email (not a log line) is delivered; delivery covered by an
  SMTP-mocked test; secrets come from env, never compose defaults.

### `[ ]` #3 — Enforce email verification in production
- **Current state:** `EMAIL_VERIFICATION_REQUIRED` defaults `False`
  (`config.py:52`, `docker-compose.yml:67`). The verification flow itself is
  complete and tested (`tests/test_auth_flows.py` L70,102,164) — it is simply not
  enforced as the default.
- **Scope:** Flip `EMAIL_VERIFICATION_REQUIRED=true` for production; verify the
  register → verify → login path end-to-end against #2.
- **Files:** `config.py`, `docker-compose.yml`, `app/api/routes/auth.py`.
- **Acceptance:** a fresh account cannot log in until its email token is redeemed;
  the distinct `email_not_verified` 403 path is exercised in a production-shaped test.

### `[ ]` #4 — Durable background job queue
- **Current state:** Pipeline processing is fire-and-forget
  `asyncio.create_task(_process_document_background(...))` at `documents.py:188`
  and `documents.py:368`, plus `gateway.py:123`. No queue or persistence across
  restart — an interrupted process strands docs in `processing`, with only the
  manual `/reprocess` endpoint as a remedy (`ROADMAP.md:184-186`).
- **Scope:** Replace with Redis/RQ or Celery. Reclaim docs stuck in `processing` on
  startup; keep `/reprocess`.
- **Acceptance:** restart mid-job does not strand documents; a doc left in
  `processing` is auto-recovered; jobs are durable across instances.

### `[ ]` #5 — Secrets management + TLS for production
- **Current state:** Postgres password is a hardcoded default `change-me`
  (`docker-compose.yml:16,57`); no TLS in front of the stack.
- **Scope:** Real secrets management for DB passwords / API keys / OCR + email
  creds (no defaults in compose) and a reverse-proxy TLS layer for production.
- **Acceptance:** `change-me` removed; production secrets come from a vault/env; TLS
  terminates at a reverse proxy.

### `[ ]` #6 — Distributed / durable rate limiting
- **Current state:** Upload limiter is an in-process `InMemoryRateLimiter(...)`
  (`auth.py:98-101`, `core/ratelimit.py:19`) — single worker, reset on
  restart/multi-instance.
- **Scope:** Move counters to a shared store (Redis) so the limit is durable and
  cross-instance.
- **Files:** `medical-bill-backend/app/core/ratelimit.py`, `app/core/auth.py`,
  `app/config.py`, `docker-compose.yml`.
- **Acceptance:** rate-limit state survives restart and is shared across workers
  (test with 2 workers).
---

## Data & Models — (real data + model quality · next ~30 days)

### `[ ]` #7 — Real CMS / fair-price benchmarks
- **Current state:** `fair_price` derives from a 33-code synthetic table with a flat
  $100 fallback for unknown codes (`data-extraction-service/app/ml/synthetic_data.py`
  L106); payer/POS/geography features now derive from the bill.
- **Acceptance:** real CMS pricing replaces the synthetic table; unknown codes use a
  documented fallback; tests updated.

### `[ ]` #8 — Collect & annotate real de-identified medical bills
- Unlocks `#9` and shares the fixture corpus from `#17`. Produce labeled
  gold-standard JSON (codes, amounts, denials, flags, appeal outcome).

### `[ ]` #9 — Retrain pricing & appeal models on real data
- **Current state:** the reported 0.97 accuracy / 0.98 AUC in
  `models/pricing_anomaly_metrics.json` is a train/test split of one synthetic
  distribution labeled by explicit rules — **not real performance**
  (`ROADMAP.md:149-151`). Re-train only after `#8` (and ideally `#10`).

### `[ ]` #10 — Finish deriving all scoring features from the bill
- Substitute real bill derivation for the remaining invented features so retrained
  models consume ground truth rather than placeholders (the constant-feature gap was
  already closed for geography/provider-type/payer; the fair-price and any remaining
  synthetic features follow).

### `[ ]` #11 — Full CMS ICD-10 / CPT reference data loading
- **Current state:** The loader has a known routing bug — `_load_cms_csv` keys on
  `code[0].isalpha()` but is passed `None` for the ICD-10/modifier alpha maps, so a
  full `icd10.csv` loads **zero** codes silently and alpha modifiers are dropped
  (`reference_data.py:207-209,235-236`; `ROADMAP.md:76,191`). Tests exist only for
  the proxy bundle (`tests/test_reference_cms_loading.py`).
- **Acceptance:** full CMS files load with validation; a zero-row load fails loudly;
  alpha ICD-10/modifier codes are preserved; the loader is covered by tests.

---

## Rules Engine

### `[ ]` #12 — Place-of-service (POS) validation rules
- **Current state:** `place_of_service` is now in the parsed-bill schema
  (`data-extraction-service/app/models/parsed_bill.py:206`), but no POS validation
  rules exist.
- **Acceptance:** a POS that contradicts the CPT code/service is flagged; unknown
  codes produce no false high flags; tests added.

### `[ ]` #13 — ICD ↔ CPT compatibility checks
- **Current state:** code-to-diagnosis compatibility is unchecked anywhere
  (`ROADMAP.md:172-173`).
- **Acceptance:** a compatibility pass flags a mismatch; tests added; existing
  Rust `#[test]` suite still passes.

### `[ ]` #14 — Data-driven NCCI loader
- **Current state:** NCCI unbundling uses **113 hardcoded pairs**
  (`bill_rules/src/types.rs` L105-250, `ROADMAP.md:55,172-173`).
- **Scope:** Replace hardcoded pairs with a loader over an editable data file (or a
  CMS NCCI edit set).
- **Files:** `bill_rules/src/types.rs`, `bill_rules/src/rules/unbundling.rs`,
  `bill_rules/src/engine.rs`.
- **Acceptance:** new data files load without a rebuild; unknown codes are handled
  conservatively.

### `[ ]` #15 — Broader modifier appropriateness rules
- **Current state:** a basic modifier-appropriateness guard just landed (commit
  `7c23bd9`); comprehensive CPT/modifier rules remain.
- **Acceptance:** a wider set of modifier↔CPT rules lands with tests; unknown codes
  produce no false high flags.

---

## Reliability & Testing

### `[ ]` #16 — Surface degraded mode clearly in UI + API
- **Current state:** every service failure silently falls back to mock/un-enriched
  data (`extraction_client.py:78-109`, `rules_engine.py:51-79`); a disabled/broken
  config is indistinguishable from a working one (`ROADMAP.md:115-118`).
- **Acceptance:** a `degraded`/`mode` field is exposed in API responses and rendered
  as a clear banner in the UI; a disabled-service test asserts the flag is set.

### `[ ]` #17 — Real document fixture corpus (PDFs, images)
- **Current state:** every test input is a synthetic Python string literal; there is
  **not a single PDF, PNG or JPG anywhere in the repo** (`ROADMAP.md:188-193`); the
  e2e smoke test uploads a 27-byte fake PDF.
- **Scope:** a small, fully de-identified corpus (text PDFs, a scanned PDF, a couple
  of PNG/JPG images, an EOB) with per-fixture gold JSON.
- **Acceptance:** ≥1 fixture per format; gold JSON per fixture; ingestion +
  extraction + rules tests run against the corpus.

### `[ ]` #18 — Tests & mocks for the LLM extraction path
- **Current state:** the LLM extraction path has zero tests and zero mocks
  (`ROADMAP.md:190`); only the deterministic heuristic fallback
  (`extractor.py:419`) is exercised.
- **Files:** `data-extraction-service/app/services/extractor.py`.
- **Acceptance:** a mocked LLM client drives the schema-constrained path; tests
  assert schema conformance, provenance, low-confidence/handwriting flags; a
  simulated provider failure falls back gracefully.
---

## Frontend

### `[ ]` #19 — Accessibility fixes
- Missing `:focus-visible`/`:focus`, collapsed nav (≤1024px icon rail) has no
  `aria-label`, sidebar never hides ≤640px with no hamburger; only 3 `for=` across
  17 form controls; eight `<h1>` elements + one `<h2>` in `app.html`; `login.html`
  has no landmarks; `#cbd5e1` text on white ≈ 1.5:1 contrast (`ROADMAP.md:196-203`).
- **Acceptance:** axe/accessibility scan passes; keyboard focus visible; nav has
  accessible names; single `h1`; contrast ≥ 4.5:1.

### `[ ]` #20 — Real audit timeline (instead of hardcoded steps)
- **Current state:** the frontend audit "timeline" is a hardcoded 5-step template,
  not live events (`ROADMAP.md:46-47`). The backend pipeline already produces a
  structured audit (`pipeline.py:210-216`); the UI should render those real events.
- **Acceptance:** timeline items come from the backend audit; no hardcoded steps.

### `[ ]` #21 — Appeal letter always from the verified backend path
- **Current state:** a previous risk was client-side template generation
  (`app.js:1354-1406`); save/re-verify now routes edited letters through the backend
  verifier (`app.js:1583-1586`). Confirm there is no surviving path that sends an
  un-verified letter, and add a test pinning the fallback-reverify behavior.

### `[ ]` #22 — Mobile / responsive improvements
- Sidebar & nav behavior on small screens (see `#19` for the a11y half).

---

## Ops & Production

- `[ ]` **#23 CI/CD** — automated test runs, builds, deployment for the four services.
- `[ ]` **#24 Monitoring & observability** — metrics, structured logging, alerting
  beyond the existing audit trail.
- `[ ]` **#25 Production CORS allow-list** — dev CORS is an explicit localhost
  allowlist (`config.py:75-78`); production must enumerate real origins, never `*`
  with `allow_credentials=True`.
- `[ ]` **#26 Kubernetes / production deployment manifests** (optional) — Compose
  exists; full orchestration still open.

---

## Decision needed — (decide before any real letter)

### `[ ]` #27 — Citation policy for appeal letters
- **Type:** product decision (allow-list + verification gate already exist).
- **Current state:** `CITATION_FABRICATION_POLICY = "off"` with an empty
  `ALLOWED_CITATIONS` by default (`config.py:70-71`); the verifier inspects
  citations only when the policy is `"warn"`. Tests cover the mechanics
  (`tests/test_letter_citations.py`).
- **Options:**
  - **A.** Fixed library of pre-approved citations (curated, legally reviewed),
    set `CITATION_FABRICATION_POLICY=warn` + populate `ALLOWED_CITATIONS`.
  - **B.** Verify citations against a maintained reference corpus before approval.
  - **C.** Omit citations entirely (safest, least useful).
- **Why it gates:** the verifier never validated statutory/regulatory references and
  cannot detect a real number used in the wrong context (`letter_verifier.py`
  L187-195); a fabricated statute sent to a payer is the highest-liability failure
  mode.
- **Acceptance:** the chosen policy is recorded; generated letters cannot carry an
  unapproved/unverifiable citation; tests updated to the chosen mode.
---

## 2-week sprint board view

| Sprint phase | Items |
|---|---|
| **Decide now** | #27 citation policy |
| **Spike/parallel** | #5 secrets+TLS · #6 distributed rate limit · #13 ICD↔CPT · #14 NCCI loader · #12 POS · #15 modifiers · #16 degraded mode |
| **Long-pole ingestion** | #1 OCR · #17 fixture corpus (seeds #8) |
| **Auth/email gate** | #2 real SMTP · #3 enforce verification |
| **Reliability** | #4 durable queue · #18 LLM tests |

Cross-cutting note: `#17` (fixtures) is the free win — it simultaneously feeds OCR
validation, e2e tests, annotation (`#8`), and later model retraining (`#9`).

## Service ownership matrix

| Service | Items |
|---|---|
| Backend (`medical-bill-backend`) | #2, #3, #4, #5, #6, #16, #21, #24, #25 |
| Extraction/Ingestion (`data-extraction-service` + ingestion) | #1, #8, #10, #11, #18 |
| Rules engine (`bill_rules`) | #12, #13, #14, #15 |
| Data/ML | #7, #8, #9, #10, #11 |
| Frontend | #16, #19, #20, #21, #22 |
| Ops/DevEx | #23, #24, #25, #26 |
| Cross-cutting decision | #27 |

## Priority index

- **0 = do before real patient bills:** #1, #2, #3, #4, #5, #6.
- **H = real data + model quality:** #7, #8, #9, #10, #11.
- **M = rules + reliability:** #12, #13, #14, #15, #16, #17, #18.
- **P = polish/ops:** #19, #20, #21, #22, #23, #24, #25, #26.
- **D = decision-first:** #27.