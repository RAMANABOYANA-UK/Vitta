# Vitta — Frontend & UX: Ticket Drafts

> Companion to `BACKLOG.md` (items #19–#22). Paste-ready drafts for a tracker.
> Line references are accurate as of 2026-08-26.

---

## Ticket #19 — Accessibility fixes

- **Priority:** Polish · **Owner:** Frontend · **Depends on:** none (cheap to
  parallelize).

### Current state — some fixes already landed
Several items flagged in the original ROADMAP audit have been fixed since:
- `aria-label` on the workspace switch (`app.html:33`), and the app nav already has
  `aria-label="App navigation"` (`app.html:38`).
- Search input has `aria-label="Search"` (`app.html:110`); Notifications/Help icon
  buttons have `aria-label` (`app.html:112,116`); action checks have
  `aria-label="Toggle action"` (`app.js:1814`).
- The login form has proper `for=` labels for Name/Email/Password
  (`login.html:324,331,338`).

### What still needs fixing (confirmed from the CSS/HTML + ROADMAP:196-203)
1. **No `:focus-visible`/`:focus` rule** in either stylesheet — keyboard focus is
   browser-default only (`styles.css`/`app.css`).
2. **Collapsed nav lacks accessible names.** At ≤1024px the sidebar collapses to a
   72px icon rail where `.nav-label` is hidden (`css/app.css:1369`) and the
   `nav-item` buttons have **no `aria-label`**, so the controls lose their name.
3. **No mobile sidebar** — the sidebar is never hidden at ≤640px and there is **no
   hamburger** in `app.html` (ties to #22).
4. **Multiple `<h1>`s** — `app.html` has eight `<h1>` and one `<h2>`; should be a
   single `<h1>` with ordered heading levels.
5. **Contrast** — `--slate-300: #cbd5e1` (`styles.css:21`) used as text on white is
   ≈1.5:1, far below the 4.5:1 AA threshold (e.g. the demo hint in `login.html:357`).

### Goal
`app.html`, `login.html`, and `index.html` pass an axe/accessibility scan; keyboard
navigation is fully usable; heading structure and contrast meet WCAG AA.

### Approach / scope
1. Add global `:focus-visible` styles (visible ring, meets contrast) to both
   stylesheets.
2. Add `aria-label` to every `nav-item` button (they are icon-only when collapsed).
3. Give every form input a `for=` label (audit all controls, not just the three now
   covered).
4. Normalize headings: one `<h1>` per page, correct `<h2>`/`<h3>` order.
5. Replace `#cbd5e1`-as-text usages with a contrast-compliant token (≥4.5:1).
6. Add landmarks to `login.html` (it currently has none) and close remaining ARIA
   gaps on `app.html`.

### Acceptance criteria
- [ ] `:focus-visible` visible on all interactive elements.
- [ ] `app.html` has a single `<h1>`; all icons have accessible names.
- [ ] Every form control has an associated `<label for>`.
- [ ] No text uses a sub-4.5:1 contrast color (axe scan passes).
- [ ] Keyboard can reach and activate every action (nav, modals, letter buttons).

### Files to touch
- `frontend/css/app.css`, `frontend/css/styles.css`
- `frontend/app.html`, `frontend/login.html`
- `frontend/js/app.js` (if toggling dynamic headings/labels)

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Changing heading tags breaks JS selectors | Audit `getElementById`/query selectors for headings before renaming |
| Focus styles clash with brand | Use the existing primary/accent token for the ring |

### First step
Run the app through axe (or Lighthouse a11y) to get a current baseline, then land
the `:focus-visible` + heading/contrast fixes first (largest, lowest-risk wins).

---
## Ticket #20 — Real audit timeline (instead of hardcoded steps)

- **Priority:** Polish · **Owner:** Frontend + Backend (API) ·
  **Depends on:** the backend already provides the data.

### Current state
The frontend audit "timeline" is a **hardcoded 5-step template**, not live events
(`ROADMAP.md:46-47`). Meanwhile the backend already builds a real, structured audit:
- The pipeline writes `audit` with timings, extraction path, rules status, flags, and
  letter verification (`medical-bill-backend/app/services/pipeline.py:210-216`),
  attached to the persisted `ParsedBill` (`schemas.py:81`).
- `AccessLog` is explicitly described as "the real data source for the frontend
  timeline" (`medical-bill-backend/app/models.py:63`), recording which user/action
  and timestamps.
- The status adapter already synthesizes per-stage progress
  (`frontend_adapter.py:664-687` `to_pipeline_status` stages).

So the data exists end-to-end; only the UI renders a static template instead of it.

### Goal
The timeline renders **real backend events** — uploaded → extraction → validation →
scoring → letter → verification — with timestamps and, where present, the
`AccessLog` actor/action trail, with **no hardcoded steps**.

### Approach / scope
1. Add/advertise a small timeline endpoint (or reuse the document audit in the
   detail response) returning ordered events `{ stage, status, timestamp, detail }`.
2. Map the pipeline `audit` + `AccessLog` into that event list in
   `frontend_adapter.py`.
3. Replace the hardcoded timeline renderer in `app.js` to build the list from the
   response (falling back to "not available" rather than fake steps).
4. Keep the degraded/sample banner semantics (#16): an unpopulated timeline shows
   honestly rather than inventing steps.

### Acceptance criteria
- [ ] Timeline items come from backend data, not a hardcoded template.
- [ ] Stages show real timestamps/status; empty/failed stages are honest.
- [ ] An unpopulated timeline says "no audit events" rather than showing fake steps.
- [ ] `tests/test_frontend_adapter.py` covers the new timeline mapping.

### Files to touch
- `frontend/js/app.js`
- `medical-bill-backend/app/services/frontend_adapter.py`
- `medical-bill-backend/app/api/routes/documents.py` (expose audit/timeline)
- `medical-bill-backend/tests/test_frontend_adapter.py`

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Backend events are coarse (status-level) | Map status transitions + AccessLog actions into granular steps |
| Timeline floods with poll events | Exclude per-poll `job_status` from AccessLog (already excluded, `gateway.py:150-153`) |

### First step (spike)
Add a `to_timeline(bill, access_logs)` helper in `frontend_adapter.py` and unit-test
it against a fixture audit; then render that list in `app.js`.

---
## Ticket #21 — Appeal letter always comes from the verified backend path

- **Priority:** Polish (safety-adjacent) · **Owner:** Frontend + Backend ·
  **Depends on:** #27 (citation policy) for citation handling, but the path itself
  can be confirmed independently.

### Current state — partially addressed
The original risk was a **client-side template literal** generating the letter shown
to the user, bypassing the backend verifier (`ROADMAP.md:45-46`, `js/app.js:1354-1406`).
Since then the code has moved toward honesty:
- `renderLetterVerification` (`app.js:1524-1528`) **withholds a verdict** for the
  client-side fallback template rather than implying a check never ran.
- "Save & re-verify" routes the edited letter through the **backend verifier**
  (`app.js:1583-1586`), which reconciles against the source bill
  (`letter_verifier.py` + `PATCH /documents/{id}/letter`).

### What remains (the confirmation + hardening)
- **Confirm** there is no surviving path where a letter can be sent / "Mark as
  sent"ed without backend verification.
- Ensure the *primary* generated letter also comes from the backend's grounded
  generator (`letter_generator.py`), not the client template — so the default
  artifact is verified, not just edited ones.
- Pin the fallback-reverify behavior with a test (edited letter → verifier → updated
  `verification_passed`/`problems`), and a test that an unverified letter cannot be
  marked sent.

### Goal
No letter reaches "send" without a backend-verification pass; the client template is
either routed back through the backend or removed as a generation source.

### Approach / scope
1. Trace every letter render/send path in `app.js` and confirm each passes through
   the backend verifier on the way to "Mark as sent".
2. Add/keep `verification_passed` gating on the send action (block or warn unless the
   backend reports a clean pass).
3. Make the primary letter come from `letter_generator.py` output via the API, and
   demote/remove the client-side template (`app.js:1354-1406`).
4. Add tests: (a) edited-letter re-verify flow, (b) unverified letter cannot be sent,
   (c) the client template path (if kept as a fallback) stays explicitly
   unverified-with-no-verdict.

### Acceptance criteria
- [ ] No letter can be marked sent without a backend `verification_passed`.
- [ ] The primary letter is backend-generated or, if a client fallback is kept, it
      is visibly unverified and cannot be sent as clean.
- [ ] Tests pin the re-verify and send-gate behaviors.
- [ ] `#27` citation policy does not reintroduce an unverified citation path.

### Files to touch
- `frontend/js/app.js`
- `medical-bill-backend/app/api/routes/documents.py` (letter/send guard)
- `medical-bill-backend/app/services/letter_verifier.py`
- `medical-bill-backend/app/services/letter_generator.py`
- `medical-bill-backend/tests/test_letter_verification_gate.py`

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Locking the UI behind a strict verifier | Use existing `verification_passed` + `problems`; block send on unresolved problems |
| Removing the client template breaks offline demo | Keep a clearly-labeled unverified fallback rather than silent bypass |

### First step
Trace + test the "edited letter → re-verify → send" path end-to-end; add a test that
an unverified letter cannot be marked sent.

---
## Ticket #22 — Mobile / responsive improvements

- **Priority:** Polish · **Owner:** Frontend · **Depends on:** pairs with #19.

### Current state
`app.css` has responsive blocks (`@media (max-width: 640px)` at `app.css:1414`;
`styles.css` responsive at `:642`, `:656`), but the app shell has gaps on small
screens: the **sidebar is never hidden at ≤640px** and there is **no hamburger** in
`app.html` (ROADMAP:199-200), so the app is cramped/unusable on phones. The collapsed
72px icon rail at ≤1024px (`app.css:1369`) also lacks full tap-target sizing.

### Goal
The dashboard is usable and legible on ≤640px: a collapsible/slide-in sidebar with a
hamburger toggle, readable padding, and adequate tap targets (≥44px).

### Approach / scope
1. Add a hamburger button (with `aria-label`, pairs with #19) that toggles the
   sidebar on small screens; hidden by default on desktop.
2. Add `@media (max-width: 640px/768px)` rules to slide the sidebar off-canvas and
   overlay the app content.
3. Increase tap-target and spacing on `nav-item`/icon buttons.
4. Ensure the degraded-mode banner, letter actions, and flag cards reflow without
   horizontal scroll.
5. Verify with a mobile viewport check (DevTools / axe).

### Acceptance criteria
- [ ] At ≤640px the sidebar is hidden and a hamburger reveals it.
- [ ] No horizontal scroll on common views (overview, bill, letter) at 360–640px.
- [ ] Primary interactive targets ≥44px.
- [ ] Hamburger has an `aria-label` (and `aria-expanded` where applicable).

### Files to touch
- `frontend/app.html`
- `frontend/js/app.js` (toggle state)
- `frontend/css/app.css`

### Risks / mitigations
| Risk | Mitigation |
|---|---|
| Toast/modals overflow on phones | Constrain modals to viewport width; test at 360px |
| Toggle state out of sync | Keep a single `aria-expanded`/class source of truth |

### First step
Add the hamburger + `@media (max-width: 640px)` off-canvas sidebar, then run a 360px
viewport pass to catch overflow.

---

## Frontend — dependency & sequencing note

```
#19 a11y  ──▶ #22 mobile (shared sidebar/hamburger work, do together)
#20 timeline ◀── backend audit + AccessLog (data already exists)
#21 letter path ──▶ #27 citation policy (verification + citations)
```

The sidebar/hamburger, `aria-label`, focus, and tap-target work in #19 and #22 is one
contiguous UI change — worth doing in a single sprint. #20 is mostly a renderer swap
on top of data that exists. #21 is the safety-critical one and should pair with
deciding #27.