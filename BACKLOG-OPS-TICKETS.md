# Vitta — Ops & Production, and the Citation Decision: Ticket Drafts

> Companion to `BACKLOG.md` (items #23–#27). Paste-ready drafts for a tracker.
> Line references are accurate as of 2026-08-26.

---

## Ticket #23 — CI/CD pipeline

- **Priority:** Ops (P5) · **Owner:** Ops/DevEx · **Depends on:** none.

### Current state
There is **no CI/CD**: no `.github/` directory, no workflows run tests or builds,
and nothing automates deployment. The repo has solid per-service test suites
(`pytest-backend.ini`, `pytest-extraction.ini`, `pytest.ini`, and the Rust `#[test]`
suite in `bill_rules`) and Dockerfiles for all four services (`docker-compose.yml`),
but they only run locally/tagged. Nothing gates a PR or releases a build.

### Goal
A CI pipeline that runs all test suites + build checks on every commit/PR, and a
CD step that builds and pushes images / deploys to a target environment.

### Approach / scope
1. **CI (lint + tests + build):** add a GitHub Actions workflow (`.github/workflows/`)
   that, on PR/push:
   - Python backend: run `pytest` with the existing configs.
   - Extraction service: run its pytest suite.
   - Rust rules: `cargo test` + `cargo clippy`/`fmt`.
   - Frontend: run a JS syntax/build check.
   - `docker build` each of the four services to catch Dockerfile regressions.
2. **Secret guard** (ties to #5): fail on committed secrets / `change-me` defaults.
3. **CD (later):** on a tag/`main`, build + push images to a container registry and
   deploy via a future orchestrator (#26) or compose stack.

### Acceptance criteria
- [ ] PR runs backend + extraction + Rust test suites; fail on error.
- [ ] Docker build of all four services passes in CI.
- [ ] A secret-scan/lint stage failing blocks the PR (especially `change-me`).
- [ ] (CD) a tag triggers an image build+push; documented deploy step.

### Files to touch
- New: `.github/workflows/ci.yml`, (later) `.github/workflows/cd.yml`
- Add `scripts/secret_scan.py` (or reuse an existing linter)

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| CI green but prod fails (env drift) | Use the same Dockerfiles in CI and CD |
| Tests slow (Rust build) | Cache cargo target via GitHub Actions caching |

### First step
Add a minimal CI workflow that runs the three existing test suites; wire a
secret-scan stage; prove green on a push.

---

## Ticket #24 — Monitoring & observability

- **Priority:** Ops (P5) · **Owner:** Backend + Ops · **Depends on:** none (can
  start with metrics/logging; alerting later).

### Current state — logging exists
- The backend has structured-ish logging at `medical-bill-backend/app/main.py:18-22`
  (`logging.basicConfig` with a `name|message` format), and the pipeline logs each
  stage with timings/path (`pipeline.py:106-108`, `service` docstring), recorded into
  the `audit` object.
- There is an `AccessLog` append-only trail (`models.py:62-67`).
- **Gaps:** no metrics endpoint (Prometheus/`/metrics`), no per-request tracing or
  request-ID correlation, no structured JSON log format for log-aggregation/alerting,
  and no alerting rules. The `audit` trail is per-document, not per-system-health.

### Goal
System health is observable: HTTP/metrics endpoints, structured (JSON) logs with
correlating `request_id`/`document_id`, and a base alerting path on the key signals
(rules/extraction down, pipeline failures, 5xx rate).

### Approach / scope
1. Add `/metrics` (Prometheus) to the backend (and optionally the extraction
   service) exposing request count, latency, 5xx, and pipeline-failure counters.
   Protect/scope it appropriately (don't expose PHI).
2. Adopt structured JSON logging with a common schema:
   `{ts, level, logger, request_id, document_id?, event, ...}`; generate a
   `request_id` per request and thread it through the pipeline.
3. Add minimal alerting rules/signals to key off `/health` (ok/degraded) and error
   counters; document where alerts hook (Ops tool, email).
4. Keep the `AccessLog` audit trail as the compliance/access record (unchanged).

### Acceptance criteria
- [ ] `/metrics` returns Prometheus-format counters (requests, latency, 5xx, failures).
- [ ] Logs are structured JSON with a `request_id` correlation field.
- [ ] `/health` outcome is factored into an alerting signal, with a documented alert.
- [ ] No PHI in metrics/logs (all values are counts/durations).

### Files to touch
- `medical-bill-backend/app/main.py` (logging config, `/metrics`)
- `medical-bill-backend/app/services/pipeline.py` (structured events)
- New: `medical-bill-backend/app/core/observability.py`
- `medical-bill-backend/requirements.txt` (prometheus-client)
- `docker-compose.yml` (metrics scrape, optional)

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Metrics leak PHI | Only counts/durations; never bill content; review logger fields |
| High cardinality from per-doc fields | Keep label cardinality bounded (document_id only on error logs) |

### First step
Add `prometheus_client` + a minimal `/metrics` (request count/latency/5xx) and a
request-`request_id` middleware; then migrate the most-visited logs to the JSON
format.

---
## Ticket #25 — Production CORS allow-list

- **Priority:** Ops · **Owner:** Backend/Ops · **Depends on:** #5 (prod config) for
  the deployed origin list.

### Current state
- The **backend app** already uses an explicit, non-wildcard allowlist:
  `CORS_ALLOWED_ORIGINS` (`config.py:75-78`) parsed by `cors_origins_list`
  (`config.py:80-88`), wired into `CORSMiddleware` with `allow_credentials=True`
  (`main.py:61-65`). A wildcard is deliberately refused (`main.py:57-60`).
  `docker-compose.yml:70` defaults the list to localhost origins.
- **Remaining gap 1:** the **Rust rules service** (`bill_rules/src/main.rs:57-61`)
  sets `CorsLayer::new().allow_origin(Any).allow_methods(Any).allow_headers(Any)` — a
  permissive wildcard. It's an internal service, but if it is ever exposed it should
  not allow any origin.
- **Remaining gap 2:** production must enumerate the **real** origins (the deployed
  frontend domain), not localhost defaults; a CI/secret guard (from #5/#23) should
  ensure prod never ships with localhost-only or a wildcard.

### Goal
Production CORS is an explicit allow-ist of real origins; the Rust service either
restricts its CORS or stays network- isolated so the wildcard is never reachable for
a browser.

### Approach / scope
1. For the backend: set `CORS_ALLOWED_ORIGINS` in prod to the actual frontend
   origin(s); keep `allow_credentials=True` with those explicit origins (never `*`).
2. For the Rust service: either restrict `CorsLayer` to the backend's origin (or
   configured list) or confirm + document it is only reachable inside the compose
   network (`docker-compose.yml` exposes it internally at `3001`, not published).
3. Add a CI check that production env CORS is a non-wildcard, non-localhost-only list.

### Acceptance criteria
- [ ] Prod backend CORS lists real origins (no wildcard, no localhost-only).
- [ ] Rust service CORS is either restricted or provably network-isolated.
- [ ] A CI/env guard fails on a wildcard or empty CORS in prod.

### Files to touch
- `medical-bill-backend/app/config.py`, `.env.example`
- `bill_rules/src/main.rs` (if restricting CORS)
- `docker-compose.yml`
- New CI env-guard (ties to #23)

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Blocking a legit origin | Keep the list env-driven and documented |
| Rust wildcard reachable | Publish `bill_rules` only inside the compose network; restrict if exposed |

### First step
Restrict the Rust `CorsLayer` to an explicit origin (or the backend) and add the CI
env-guard; then set real prod origins.

---

## Ticket #26 — Kubernetes / production deployment manifests (optional)

- **Priority:** Ops (optional) · **Owner:** Ops/DevEx · **Depends on:** #23, #5.

### Current state
Deployment today is **Docker Compose** (`docker-compose.yml`): Postgres + four
services with healthchecks and explicit depends_on. There are **no K8s manifests**
(no `k8s/`/`deploy/` directory). Full production orchestration (scaling, rolling
updates, secrets volumes, autoscaling) is open.

### Goal (optional, per-backlog)
Provide K8s manifests that deploy the compose topology: `deployment`, `service`,
`configmap`, and `secret` objects for the four services + Postgres, with the same
healthchecks.

### Approach / scope
1. Translate `docker-compose.yml` into a `k8s/` chart or plain manifests
   (deployment + service per service; a Postgres StatefulSet or use a managed DB).
2. Mirror env vars from compose into `ConfigMap` (non-secret) and `Secret`
   (DB password, API keys — ties to #5).
3. Add resource requests/limits, liveness/readiness probes (reuse `/health`),
   and `restartPolicy`.
4. Keep it optional/manual — no hard requirement to adopt K8s if Compose suffices.

### Acceptance criteria
- [ ] Manifests deploy all four services + DB with healthchecks.
- [ ] Secrets come from `Secret`/env, not plaintext in manifests.
- [ ] Optional: a `kubectl apply -k k8s/` works in a test cluster.

### Files to touch
- New: `k8s/` (or `deploy/`) manifests/config
- Optionally a `Dockerfile` tweak for env

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Scope creep / over-engineering | Keep it an optional spike; Compose remains the supported path |
| Secret handling in manifests | Reference `Secret` objects; never inline secrets |

### First step
Spike converting the `backend` + `extraction` + `bill_rules` services into a minimal
`k8s/` deployment set, reusing `docker-compose.yml` env and `/health` probes.

---
---

## Decision — Ticket #27: Citation policy for appeal letters

- **Priority:** Decision-first (unblocks every letter sprint) · **Owner:** Product +
  Legal + Engineering · **Depends on:** none (the gate already exists).

### Current state
A citation-fabrication guard already exists:
- `CITATION_FABRICATION_POLICY` defaults `"off"` with an empty `ALLOWED_CITATIONS`
  (`config.py:70-71`); when `"warn"`, any statutory/regulatory citation **not** in
  `ALLOWED_CITATIONS` fails verification.
- Tests cover the mechanics (`tests/test_letter_citations.py`: regex matches,
  plain-number ignore, policy-on allows approved, unapproved flagged, off ignores).
- The verifier checks codes/dates/NPIs/amounts but not the *semantic* correctness of
  a citation; it can't detect a real number used in the wrong context
  (`letter_verifier.py:187-195`).

So the engineering is ready — the remaining work is a **product/legal decision**, not
a build.

### The decision — pick ONE

**Option A — Fixed allow-list (recommended default).**
- Maintain a small, legally-reviewed library of approved citation strings.
- Set `CITATION_FABRICATION_POLICY=warn` and populate `ALLOWED_CITATIONS`.
- Letters may only reference an approved citation; anything else fails verification.
- Pros: deterministic, safe, cheap. Cons: limited expressiveness.

**Option B — Verify against a reference corpus.**
- Maintain a corpus of statutes/regs; verify any citation against it (semantic + text).
- Pros: more flexible. Cons: needs a maintained corpus + a verifier; higher liability
  surface; more work.

**Option C — Omit citations entirely.**
- Generated letters never include statutory/regulatory citations.
- Pros: zero fabrication risk. Cons: less persuasive/grounded appeal letters.

### Goal / decision criteria
Decide A/B/C and record the policy. Then the minimal engineering follows:
- If **A** → set `warn` + populate `ALLOWED_CITATIONS`; verify letters model the
  allow-list.
- If **B** → build/extend a corpus + citation-verification path.
- If **C** → strip citations from the generator/template, keep the guard as defense.

### Acceptance criteria
- [ ] A written decision (A/B/C) is recorded with rationale.
- [ ] The chosen policy is set in config; letters cannot carry an unapproved/
      unverifiable citation.
- [ ] `tests/test_letter_citations.py` passes with the chosen mode.
- [ ] The decision is reflected in `#21` (letter path) so no citation bypasses it.

### Files to touch
- `medical-bill-backend/app/config.py` (`CITATION_FABRICATION_POLICY`,
  `ALLOWED_CITATIONS`)
- `medical-bill-backend/app/services/letter_generator.py` (strip if C)
- `medical-bill-backend/tests/test_letter_citations.py`
- Docs: ROADMAP decision record

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Picking a policy that limits usefulness | Align with legal; A as the safe default, upgrade to B only if needed |
| Citations reintroduced by templates | Gate at the generator/verifier (defense-in-depth with #21) |

### First step (decision-making, not code)
Run a short product/legal call to pick A, B, or C and write the decision into a
`docs/decisions/` ADR-style note, then wire the minimal config + tests.

---

## Ops & Decision — dependency note

```
#23 CI/CD ──▶ #24 observability (CI can gate on alerting/metrics skeleton)
#5 secrets ──▶ #25 CORS guides / #26 K8s Secret + ConfigMap
#21 letter path ──▶ #27 citation policy (verification + citations)
```

- **#23** is the highest-leverage Ops item: it makes test/build/secret regressions
  visible on every PR (and can enforce #5's "no `change-me`" rule and #25's CORS guard).
- **#24** needs only the minimal `/metrics` + structured logging to start; alerting
  hooks in later.
- **#27** is the one true *decision* — it's a product/legal call, not code, and it
  gates #21 (letter production) and the allow-list/warn config.
- **#26** stays optional; if Compose is sufficient, defer it.