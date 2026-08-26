# Vitta — Critical Backlog: Ticket Drafts

> Companion to `BACKLOG.md`. Each ticket is a paste-ready draft for a tracker
> (GitHub Issue / Linear / Jira). Frames, file touch-lists, acceptance criteria,
> risks, and a small first step ("spike") are included. Line references reflect the
> repo on 2026-08-26.

---

## Ticket #1 — Functional OCR for images & scanned PDFs

- **Priority:** Critical (P0) · **Owner:** Extraction/Ingestion ·
  **Depends on:** none (parallelizable with #2–#6) · **Unblocks:** #17, #7.

### Problem
Real-world medical bills are photos and scans. Today images and scanned (text-less)
PDFs **fail with an honest error** rather than fabricate text:
- `scanned_pdf_needs_ocr` — `medical-bill-backend/app/services/ingestion.py:249`
- `ocr_not_configured` — `medical-bill-backend/app/services/ingestion.py:267`

Support exists: `OCR_ENABLED` (`config.py:60`, `docker-compose.yml:65`) toggles the
path, `pytesseract` is imported lazily (`requirements.txt:14-16`), and the extraction
method is plumbed through as `method == "ocr"`. What's missing is a **configured,
working provider** and the result wiring.

### Goal
An uploaded JPEG/PNG/WEBP or scanned PDF yields extracted text with **source
provenance + confidence**, and the UI honestly reports OCR ran (see `frontend_adapter.py:664-687`, which already supports an `ocr_running` state).

### Approach / scope
1. **Choose provider** (decision, ~0.5d spike):
   - **Tesseract (self-hosted)** — cheapest, no PHI leaves the box, but weaker on
     degraded scans/handwriting. Requires shipping the tesseract binary in the
     Docker image (`medical-bill-backend/Dockerfile`).
   - **AWS Textract / GCP Document AI** — better accuracy and table handling, but
     PHI leaves the infrastructure boundary → needs BAA + documented config.
2. Rasterize scanned PDF pages before OCR (PyMuPDF/pypdf is already a dependency).
3. Wire `pytesseract`/provider client behind the existing `OCR_ENABLED` switch and a
   `ocr_provider` config; keep the honest error as the *unconfigured* default.
4. Propagate per-page/full-document confidence into provenance so downstream
   validation/low-confidence flags can use it.
5. Update `tests/test_ingestion.py` OCR-error tests to exercise the real path.

### Acceptance criteria
- [ ] Real image + scanned-PDF uploads produce text, not `ocr_not_configured`.
- [ ] Text-layer PDFs still read without OCR (no regression on `method == "pdf_text"`).
- [ ] Unconfigured provider still fails honestly (no silent fabric).
- [ ] OCR confidence/source is present in the extraction result and surfaced as
      low-confidence flags where appropriate.
- [ ] Tesseract-or-managed dependency installed in the Docker image if self-hosted.

### Files to touch
- `medical-bill-backend/app/services/ingestion.py`
- `medical-bill-backend/app/services/document_text.py`
- `medical-bill-backend/app/config.py`
- `medical-bill-backend/requirements.txt`
- `medical-bill-backend/Dockerfile`, `docker-compose.yml`, `.env.example`
- `medical-bill-backend/tests/test_ingestion.py`

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| PHI egress via cloud OCR | Prefer self-hosted; if cloud, require BAA + document it |
| False text extraction ("text-Layer" weld) | Confidence/provenance surfaced; keep honest-error path |
| Docker image bloat / tesseract font data | Pin a known tesseract build; keep it multi-stage |

### First step (spike)
Stand up the simplest provider (Tesseract via `pytesseract`) against 3 realistic
fixtures (one PNG, one scanned PDF, one text PDF from #17 if available), measure
accuracy, and report the recommendation (self-host vs Textract/Document AI).

---
---

## Ticket #2 — Real SMTP / transactional email sending

- **Priority:** Critical (P0) · **Owner:** Backend · **Depends on:** none ·
  **Pairs with:** #3 (enforce verification).

### Problem
The current sender is a deliberate dev-safe **"log instead of send"** boundary
(`medical-bill-backend/app/services/mailer.py:1-6`). Both senders — verification
(`send_verification_email`, `mailer.py:35-46`) and appeal letters
(`send_appeal_letter_email`, `mailer.py:49-62`) — only log. There is no SMTP /
transactional provider wired, and the docstrings leave production integration as
open.

### Goal
Verification links and appeal letters are **delivered**, not logged, with a
PHI-safe transport config and env-supplied secrets. The delivery contract the auth
routes already rely on ("produce a `verification_url` and send without raising"
— `mailer.py:7-9`) stays stable so tests keep passing with a mocked sender.

### Approach / scope
1. Introduce a `Mailer` abstraction with two backends, selected by config:
   - `log` (default, dev-only) — current behavior.
   - `smtp` / `sendgrid` / `ses` — real transport.
2. Add config: `EMAIL_PROVIDER`, SMTP host/port/user/pass or provider API key
   (secrets from env, never compose defaults — ties to #5), and a
   `DEFAULT_FROM`/`FROM_NAME`.
3. Route both `send_verification_email` and `send_appeal_letter_email` through it.
4. Keep the appeal-letter body out of logs (already preserved — only address +
   subject logged in `mailer.py:53-62`).
5. Add an SMTP-mocked test asserting a message is handed to the transport with the
   right recipient/subject/body.

### Acceptance criteria
- [ ] Verification and letter emails are sent via a configured provider, not logged.
- [ ] `log` backend still works for tests/dev; existing dev tests pass with the mock.
- [ ] Secrets come from env (no hardcoded defaults) — see #5.
- [ ] A test asserts delivery via an SMTP client mock without a live server.
- [ ] Appeal-letter body never appears in logs.

### Files to touch
- `medical-bill-backend/app/services/mailer.py`
- `medical-bill-backend/app/config.py`
- `medical-bill-backend/app/api/routes/auth.py` (if wiring changes)
- `medical-bill-backend/requirements.txt`
- `docker-compose.yml`, `.env.example`
- `medical-bill-backend/tests/test_auth_flows.py` (add SMTP-mocked delivery tests)

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Email delivery in staging burns credits / reaches real addresses | Use a dev inbox / `+suffix` addresses in non-prod |
| PHI in transit | Require TLS (STARTTLS)/TLS-only transport; envelope-only logging |
| Provider outage blocks registration | Retry/queue sends; never fail the auth response on email failure |

### First step (spike)
Wire the `log` backend behind the new `Mailer` interface with a config switch (no
behavior change), add the SMTP-mocked unit test, then implement the SMTP transport.

---
## Ticket #3 — Enforce email verification in production

- **Priority:** Critical (P0) · **Owner:** Backend · **Depends on:** #2 ·
  **Every item:** configuration + verification, not a build.

### Problem
Email verification is implemented and tested (`tests/test_auth_flows.py:70,102,164`)
but **off by default**: `EMAIL_VERIFICATION_REQUIRED=False` (`config.py:52`,
`docker-compose.yml:67`). Until it is enforced, accounts don't prove ownership of
their email — a weak gate for a PHI system.

### Goal
In production, a fresh account **cannot log in** until its emailed token is
redeemed; the distinct `email_not_verified` 403 path is exercised.

### Approach / scope
1. Default `EMAIL_VERIFICATION_REQUIRED=true` for the production env (keep the
   existing config switch, so dev stays frictionless).
2. Verify the register → verify → login flow end-to-end against the real mailer (#2).
3. Confirm the guard wiring (`auth.py:95-96` blocks login; `auth.py:134`,
   `auth.py:185-187` issue + distinct 403) still behaves under the enforced mode.
4. Add a production-shaped test: register → login refused with 403 → redeem token →
   login succeeds.

### Acceptance criteria
- [ ] With `EMAIL_VERIFICATION_REQUIRED=true`, a new account cannot log in until
      verified.
- [ ] The unverified-login 403 (`email_not_verified`) is distinct and non-revealing.
- [ ] Resend/verify endpoints work against a real (mocked) sender.
- [ ] A production-shaped test covers the full happy path.

### Files to touch
- `medical-bill-backend/app/config.py`
- `medical-bill-backend/app/api/routes/auth.py` (if guard needs hardening)
- `docker-compose.yml`, `.env.example`
- `medical-bill-backend/tests/test_auth_flows.py`

### First step
Default the flag to `true` behind the env switch and run the existing verification
tests to confirm green; then do the end-to-end run with #2.

---

## Ticket #4 — Durable background job queue

- **Priority:** Critical (P0) · **Owner:** Backend · **Depends on:** none.

### Problem
Pipeline processing is **fire-and-forget `asyncio.create_task`**:
- `medical-bill-backend/app/api/routes/documents.py:188` (upload)
- `medical-bill-backend/app/api/routes/documents.py:368` (reprocess)
- `medical-bill-backend/app/api/routes/gateway.py:123` (gateway upload)

No queue, no persistence across restart. An interrupted process strands documents
in `processing`; the only remedy is the manual `POST /reprocess` endpoint
(`ROADMAP.md:184-186`). `_process_document_background` (`documents.py:417`) already
guarantees a terminal state in a healthy run, but a process kill mid-run leaves the
DB stuck.

### Goal
Document processing is **durable**: enqueued as a persisted unit of work, retried
on worker restart, with no stranded `processing` docs.

### Approach / scope
1. Pick a queue — Redis/RQ or Celery+Redis are the lightest fits (Redis is also
   needed for #6 rate limiting and #5, so it's not additive long-term).
2. Move the three `create_task` call sites to enqueue a `(document_id, filename)`
   job and return immediately (the HTTP response keeps the current behavior).
3. Keep the existing `_process_document_background` logic as the worker handler
   (it's already correct: result persisted first, then `letter_ready`).
4. Add a startup "reclaim" sweep: any document stuck in `processing` older than a
   threshold is re-enqueued or forced to `error`.
5. Add a Postgres-backed job table if RQ's at-least-once default is insufficient
   (we want at-most-once-ish + idempotent handlers — see risks).

### Acceptance criteria
- [ ] Upload, gateway upload, and reprocess all enqueue (nothing fire-and-forget).
- [ ] Restart mid-job does not strand documents in `processing` (auto-reclaimed).
- [ ] Duplicate enqueue of the same document does not double-process (idempotent).
- [ ] A killed worker's in-flight job is picked up by another worker.
- [ ] `/_health` reports queue worker status.

### Files to touch
- `medical-bill-backend/app/api/routes/documents.py`
- `medical-bill-backend/app/api/routes/gateway.py`
- New: `medical-bill-backend/app/jobs/` (enqueue/reclaim/worker)
- `app/config.py`, `docker-compose.yml`, `requirements.txt`
- `tests/` (queue durability tests, e.g. `tests/test_queue_durability.py`)

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| At-least-once leads to double-apply of rules | Make the handler idempotent (skip if already `letter_ready`); keep result write + status change as the guard |
| Redis not durable across its own restart | RQ default is fine for short jobs; document the trade-off; optional PG-backed jobs later |
| Jobs stuck forever after crash | Startup reclaim sweep (age > threshold) |

### First step (spike)
Stand up Redis + RQ locally, move the three call sites to `.enqueue()`, and write a
durability test that kills the worker mid-job and asserts auto-reclaim. Start with
`upload  → enqueue → worker → existing pipeline`.

---
## Ticket #5 — Secrets management + TLS for production

- **Priority:** Critical (P0) · **Owner:** Backend/Ops · **Depends on:** none.

### Problem
Infrastructure defaults leak into a PHI context:
- Postgres password is a hardcoded default `change-me` (`docker-compose.yml:16,57`).
- No TLS in front of the stack (the compose file even notes a reverse proxy is
  expected — `docker-compose.yml:6-7`).
- API keys for OCR (#1), email (#2), and any cloud provider are not yet managed.

### Goal
Production runs with **no default secrets** and **encrypted** transport: DB, API,
and provider credentials come from a secrets store/env, and TLS terminates at a
reverse proxy.

### Approach / scope
1. Audit all secrets: Postgres password, `DATABASE_URL`
   (`docker-compose.yml:57`), `SECRET_*`/token signing keys, `LLM_API_KEY`
   (`config.py:33`), OCR/email provider keys.
2. Move them to env-injected secrets (`.env` for dev, a vault/secret manager in
   prod); remove every `:-change-me` fallback from compose.
3. Add a reverse proxy (Caddy/nginx/Traefik) in front of `backend`/`frontend`
   terminating TLS with cert auto-provisioning (e.g. Caddy).
4. Add a placeholder `*.secret.example` and a lint/CI check that fails on any
   committed secret or `change-me` default.

### Acceptance criteria
- [ ] No hardcoded secrets in `docker-compose.yml` or tracked config.
- [ ] Production secrets come from env/vault, verified by a CI guard.
- [ ] TLS terminates at a reverse proxy; internal traffic between services is
      inside the trust boundary.
- [ ] `scripts/secret-scan` (or CI lint) blocks commits containing known-suspect
      patterns.

### Files to touch
- `docker-compose.yml`
- `medical-bill-backend/app/config.py`, `.env.example`
- New: `deploy/` (reverse proxy config), a secrets CI check
- README ops docs

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Breaking dev ergonomics | Keep dev defaults readable but clearly dev-only; gate prod off distinct env |
| Secret leaking via logs | Redact `DATABASE_URL`/keys in logging config; never log bodies/full URLs |

### First step
Run a repo secret scan to enumerate every placeholder; remove `change-me` defaults
and gate production behind required env vars.

---

## Ticket #6 — Distributed / durable rate limiting

- **Priority:** Critical (P0) · **Owner:** Backend · **Depends on:** Redis
  (shared with #4).

### Problem
The upload limiter is **in-process** (`InMemoryRateLimiter`):
- `medical-bill-backend/app/core/auth.py:98-101` instantiates it per worker.
- `require_upload_slot` (`auth.py:104-116`) checks `_upload_rate_limiter.allow(...)`.
- `app/core/ratelimit.py:19` documents the caveat: with `uvicorn --workers N`, each
  worker enforces independently, so the effective ceiling becomes **N × the
  configured value**, and state is lost on restart.

### Goal
Rate-limit state is **shared and durable** across workers/instances via Redis, so
per-user ceilings are a true global invariant.

### Approach / scope
1. Back it with a Redis client while keeping the sliding-window semantics (or use a
   standard fixed/sliding-window Redis pattern).
2. Abstract behind the existing `allow(key) -> bool` interface so
   `require_upload_slot` (`auth.py:104`) doesn't change shape.
3. Add a config switch `RATE_LIMIT_BACKEND` (`memory` default for tests, `redis` in
   prod).
4. Keep the injectable clock / deterministic tests that `ratelimit.py` already
   supports.

### Acceptance criteria
- [ ] With 2+ workers, the combined rate is the same as a single configured limit.
- [ ] State survives a worker restart (Redis-backed).
- [ ] `memory` backend still works for tests (existing `tests/test_ratelimit.py` pass).
- [ ] A CI test spins up 2 workers and asserts the global ceiling (or a
      Redis-backed limiter keyed by the same user).

### Files to touch
- `medical-bill-backend/app/core/ratelimit.py`
- `medical-bill-backend/app/core/auth.py`
- `medical-bill-backend/app/config.py`
- `medical-bill-backend/requirements.txt`
- `docker-compose.yml`
- `tests/test_ratelimit.py` (add redis-backend tests)

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Redis becomes a new SPOF for uploads | Fail-open or degrade to in-proc on Redis outage (log loudly), or make 429 the only risk; document choice |
| Sliding-window cost on every upload | Use an atomic Lua/INCR pattern; benchmark under load |

### First step (spike)
Add an optional `redis` backend implementing the same `InMemoryRateLimiter` contract,
a config switch, and a 2-worker test that proves the ceiling is shared. Then wire
`require_upload_slot` to the selected backend.</think>Two small typos slipped in ("Secrets | Secret |" row and the broken code fence in #5, plus "is | orpus" in #6). Let me fix those and verify the final file

<｜DSML｜tool_calls>
<｜DSML｜invoke name="editor">
<｜DSML｜parameter name="new_text" string="true">- [ ] No hardcoded secrets in `docker-compose.yml` or tracked files.
- [ ] Production secrets come from env/vault, verified by CI guard.
- [ ] TLS terminates at a reverse proxy; internal traffic is inside the
      trust boundary.
- [ ] A CI guard flags commits containing known-secret patterns.