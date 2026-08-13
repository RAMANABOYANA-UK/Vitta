/* ============================================================
   VITTA — API Contract Layer + Mock Backend
   ============================================================
   This file defines the agreed API contract between the
   frontend and the ingestion/extraction/ML pipeline services.

   Endpoints (all JSON, base URL configurable):
     POST /upload                     → { jobId, documentId, status }
     GET  /jobs/{id}/status           → PipelineStatus (see below)
     GET  /bills/{id}                 → ParsedBill
     GET  /bills/{id}/flags           → FlagSet
     GET  /bills/{id}/appeal-score    → AppealScore
     GET  /codes/{code}               → CodeDefinition
     GET  /documents/{id}/pages/{n}   → PageImage (PNG/JPEG)
     WS   /ws/jobs/{id}               → stream of PipelineUpdate events

   The MockVittaAPI class below simulates the real backend with
   exactly these shapes so the UI can be built against the real
   contract, not guesses. Swap MockVittaAPI → HttpClientVittaAPI
   when the backend is live.
   ============================================================ */

(function (global) {
  "use strict";

  /* ==========================================================
     1. TYPE / CONTRACT DEFINITIONS (JSDoc shape documentation)
     ========================================================== */

  /**
   * @typedef {Object} UploadResponse
   * @property {string} jobId     — UUID for the pipeline job
   * @property {string} documentId — ID of the stored document
   * @property {"uploading"} status — initial status
   * @property {string} filename  — original filename
   */

  /**
   * @typedef {Object} PipelineStage
   * @property {"uploading"|"preprocessing"|"ocr_running"|"extraction_running"|"validation_running"|"ml_scoring_running"} name
   * @property {"pending"|"running"|"done"|"failed"|"skipped"} status
   * @property {string|null} startedAt
   * @property {string|null} completedAt
   * @property {string|null} error      — failure message (when status = failed)
   * @property {number|null} errorCode  — machine-readable failure code
   */

  /**
   * @typedef {Object} PipelineStatus
   * @property {string} jobId
   * @property {string} documentId
   * @property {"uploading"|"preprocessing"|"ocr_running"|"extraction_running"|"validation_running"|"ml_scoring_running"|"done"|"failed"} status
   * @property {number} progress       — 0–100 aggregate
   * @property {PipelineStage[]} stages
   * @property {string|null} failure   — top-level failure code/message when failed
   * @property {boolean} partial       — true if some results already available
   * @property {ParsedBill|null} partialBill   — streamed in after extraction_running
   * @property {FlagSet|null} partialFlags     — streamed in after validation_running
   * @property {AppealScore|null} partialScore — streamed in after ml_scoring_running
   * @property {Array<{page:number, message:string, severity:"info"|"warning"|"critical"}>} extractionWarnings
   */

  /**
   * @typedef {Object} BoundingBox
   * @property {number} page      — 1-based page index
   * @property {number} x         — normalized 0–1
   * @property {number} y         — normalized 0–1
   * @property {number} w         — normalized 0–1
   * @property {number} h         — normalized 0–1
   */

  /**
   * @typedef {Object} FieldVerification
   * @property {boolean} verified
   * @property {number|null} confidence  — 0–1 when verified via OCR
   * @property {string|null} method       — "ocr_high_confidence" | "ocr_low_confidence" | "manual_review" | "absent"
   * @property {string|null} note
   */

  /**
   * @typedef {Object} ICD10Code
   * @property {string} code
   * @property {string} description       — plain-language description
   */

  /**
   * @typedef {Object} LineItem
   * @property {string} id                — e.g. "li-1"
   * @property {number} page              — 1-based page
   * @property {BoundingBox} bbox         — provenance pointer back to source region
   * @property {string} serviceDate       — "2026-01-22"
   * @property {string|null} cptCode      — CPT or null if HCPCS-only
   * @property {string|null} hcpcsCode    — HCPCS or null if CPT-only
   * @property {string} code              — the primary display code
   * @property {string} codeType          — "CPT"|"HCPCS"|"ICD-10"
   * @property {string} description       — plain-language description
   * @property {number|null} units
   * @property {string[]} modifiers
   * @property {string|null} placeOfService
   * @property {ICD10Code[]} icdCodes     — diagnosis codes linked to this line
   * @property {Object} amounts
   * @property {number|null} amounts.charge
   * @property {number|null} amounts.allowed
   * @property {number|null} amounts.paid
   * @property {number|null} amounts.patientResponsibility
   * @property {Object} verification
   * @property {FieldVerification} verification.amounts
   * @property {FieldVerification} verification.description
   * @property {FieldVerification} verification.code
   * @property {FieldVerification} verification.date
   */

  /**
   * @typedef {Object} ParsedBillMetadata
   * @property {string|null} provider
   * @property {string|null} providerNpi
   * @property {string|null} payer
   * @property {string|null} statementDate
   * @property {string|null} accountRef
   * @property {string|null} memberName
   * @property {string|null} memberId
   * @property {number|null} patientLiability
   */

  /**
   * @typedef {Object} DocumentPage
   * @property {number} index              — 1-based
   * @property {string} imageUrl
   * @property {string} thumbnailUrl
   * @property {number} width
   * @property {number} height
   */

  /**
   * @typedef {Object} ParsedBill
   * @property {string} documentId
   * @property {string} jobId
   * @property {ParsedBillMetadata} metadata
   * @property {Object} totals
   * @property {number|null} totals.billed
   * @property {number|null} totals.allowed
   * @property {number|null} totals.paid
   * @property {number|null} totals.patientResponsibility
   * @property {Object} totals.reconciliation
   * @property {boolean} totals.reconciliation.ok
   * @property {number|null} totals.reconciliation.diff    — billed − (allowed + patient_resp)
   * @property {string|null} totals.reconciliation.note
   * @property {LineItem[]} lineItems
   * @property {DocumentPage[]} pages
   * @property {Array<{page:number, message:string, severity:"info"|"warning"|"critical"}>} extractionWarnings
   * @property {"complete"|"partial"} extractionStatus
   */

  /**
   * @typedef {Object} ShapContribution
   * @property {string} feature         — machine key e.g. "cpt_price_ratio"
   * @property {string} label           — human label e.g. "Charge vs regional median"
   * @property {number|null} value      — numeric value that drove the flag
   * @property {string} direction       — "up"|"down" (raised/lowered suspicion)
   * @property {string} description     — readable bullet point
   */

  /**
   * @typedef {Object} Flag
   * @property {string} id
   * @property {"duplicate_charge"|"unbundling"|"arithmetic_mismatch"|"invalid_deprecated_code"|"surprise_billing"|"pricing_anomaly"|"upcoding"|"denied_claim"|"missing_authorization"|"coverage_gap"} category
   * @property {string} title
   * @property {"high"|"medium"|"low"} severity
   * @property {number|null} confidence — 0–1
   * @property {"rule"|"ml"} detectionType
   *               rule = deterministic fact (e.g. duplicate), ml = probability/anomaly
   * @property {number|null} flagAmount — estimate of impact in USD
   * @property {string[]} lineItemIds   — related line items
   * @property {string} summary
   * @property {string} description
   * @property {Object} why             — SHAP explanation surface
   * @property {string} why.title
   * @property {ShapContribution[]} why.contributions
   * @property {Object} evidence
   * @property {string|null} evidence.codeReference
   * @property {string|null} evidence.source
   * @property {boolean} resolved        — user-dismissable
   */

  /**
   * @typedef {Object} FlagSet
   * @property {string} documentId
   * @property {Flag[]} flags
   * @property {boolean} complete       — false while ML scoring still running
   * @property {Object} summary
   * @property {number} summary.totalFlaggedAmount
   * @property {Object} summary.countByCategory
   * @property {number} summary.countByCategory.duplicate_charge
   * @property {number} summary.countByCategory.unbundling
   * @property {number} summary.countByCategory.arithmetic_mismatch
   * @property {number} summary.countByCategory.invalid_deprecated_code
   * @property {number} summary.countByCategory.surprise_billing
   * @property {number} summary.countByCategory.pricing_anomaly
   * @property {number} summary.countByCategory.upcoding
   * @property {number} summary.countByCategory.denied_claim
   * @property {number} summary.countByCategory.missing_authorization
   * @property {number} summary.countByCategory.coverage_gap
   * @property {number} summary.ruleCount
   * @property {number} summary.mlCount
   */

  /**
   * @typedef {Object} AppealFactor
   * @property {string} key
   * @property {string} label
   * @property {number} impact         — signed probability contribution (−1..1)
   * @property {"up"|"down"} direction
   * @property {string} description
   * @property {boolean} actionable
   */

  /**
   * @typedef {Object} AppealScore
   * @property {string} documentId
   * @property {number} score          — CALIBRATED probability 0–1
   * @property {boolean} calibrated
   * @property {string} modelVersion
   * @property {[number, number]} confidenceInterval  — e.g. [0.76, 0.90]
   * @property {number} sampleSize     — number of appeal policies/cases in model
   * @property {Object|null} calibration — calibration diagnostics
   * @property {number|null} calibration.expectedError
   * @property {string} basis          — readable copy e.g. "120+ appeal policies"
   * @property {AppealFactor[]} factors
   * @property {string} updatedAt      — ISO timestamp
   * @property {boolean} stale         — true if inputs changed and score needs recompute
   */

  /**
   * @typedef {Object} CodeDefinition
   * @property {string} code
   * @property {"CPT"|"HCPCS"|"ICD-10"|"Term"} type
   * @property {string} description
   * @property {string|null} plainLanguage
   * @property {string|null} category
   * @property {string|null} aka
   * @property {string|null} notes
   * @property {string|null} source    — e.g. "AMA-CMS-2026-C"
   * @property {boolean} deprecated
   * @property {string|null} supersededBy
   */

  /* ==========================================================
     2. MOCK BACKEND — Bills in ParsedBill shape
     ========================================================== */

  const rand = (min, max) => min + Math.random() * (max - min);
  const PI = 3.141592653589793;

  const PAGE_1 = { index: 1, imageUrl: "data:image/svg+xml," + encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1100">
      <rect width="800" height="1100" fill="#fff"/>
      <rect x="40" y="40" width="720" height="70" rx="8" fill="#f0fdfa"/>
      <text x="60" y="72" font-family="Arial" font-size="20" font-weight="bold" fill="#0d9488">ST. MARY'S MEDICAL CENTER</text>
      <text x="60" y="95" font-family="Arial" font-size="13" fill="#64748b">Patient Statement · Account #4821-9930</text>
      <rect x="40" y="130" width="720" height="120" rx="8" fill="#f8fafc"/>
      <text x="60" y="158" font-family="Arial" font-size="14" font-weight="bold" fill="#334155">DATE OF SERVICE: 01/22/2026</text>
      <text x="60" y="180" font-family="Arial" font-size="13" fill="#475569">MEMBER: ALEX SHARMA · ID: X-8842-001</text>
      <text x="60" y="202" font-family="Arial" font-size="13" fill="#475569">PAYER: BLUECROSS SHIELD TX · POLICY: BCS-TX-99123</text>
      <text x="60" y="224" font-family="Arial" font-size="13" fill="#475569">CLAIM: 2025-8841</text>
      <line x1="40" y1="270" x2="760" y2="270" stroke="#e2e8f0" stroke-width="2"/>
      <text x="60" y="295" font-family="Arial" font-size="12" font-weight="bold" fill="#64748b">DATE</text>
      <text x="180" y="295" font-family="Arial" font-size="12" font-weight="bold" fill="#64748b">CODE</text>
      <text x="300" y="295" font-family="Arial" font-size="12" font-weight="bold" fill="#64748b">DESCRIPTION</text>
      <text x="640" y="295" font-family="Arial" font-size="12" font-weight="bold" fill="#64748b" text-anchor="end">CHARGE</text>
      <text x="60" y="325" font-family="Arial" font-size="13" fill="#334155">01/22/26</text>
      <text x="180" y="325" font-family="monospace" font-size="13" font-weight="bold" fill="#0f766e">99283</text>
      <text x="300" y="325" font-family="Arial" font-size="13" fill="#475569">ER visit, level 3</text>
      <text x="640" y="325" font-family="Arial" font-size="13" fill="#334155" text-anchor="end">$1,450.00</text>
      <text x="60" y="355" font-family="Arial" font-size="13" fill="#334155">01/22/26</text>
      <text x="180" y="355" font-family="monospace" font-size="13" font-weight="bold" fill="#b91c1c">99284</text>
      <text x="300" y="355" font-family="Arial" font-size="13" fill="#475569">ER visit, level 4 (separate)</text>
      <text x="640" y="355" font-family="Arial" font-size="13" fill="#334155" text-anchor="end">$1,120.00</text>
      <text x="60" y="385" font-family="Arial" font-size="13" fill="#334155">01/22/26</text>
      <text x="180" y="385" font-family="monospace" font-size="13" font-weight="bold" fill="#b45309">99285</text>
      <text x="300" y="385" font-family="Arial" font-size="13" fill="#475569">ER visit, level 5</text>
      <text x="640" y="385" font-family="Arial" font-size="13" fill="#334155" text-anchor="end">$890.00</text>
      <text x="60" y="415" font-family="Arial" font-size="13" fill="#334155">01/22/26</text>
      <text x="180" y="415" font-family="monospace" font-size="13" font-weight="bold" fill="#0f766e">93005</text>
      <text x="300" y="415" font-family="Arial" font-size="13" fill="#475569">Electrocardiogram</text>
      <text x="640" y="415" font-family="Arial" font-size="13" fill="#334155" text-anchor="end">$320.00</text>
      <text x="60" y="445" font-family="Arial" font-size="13" fill="#334155">01/22/26</text>
      <text x="180" y="445" font-family="monospace" font-size="13" font-weight="bold" fill="#0f766e">81003</text>
      <text x="300" y="445" font-family="Arial" font-size="13" fill="#475569">Urinalysis, automated</text>
      <text x="640" y="445" font-family="Arial" font-size="13" fill="#334155" text-anchor="end">$145.00</text>
      <text x="60" y="475" font-family="Arial" font-size="13" fill="#334155">01/22/26</text>
      <text x="180" y="475" font-family="monospace" font-size="13" font-weight="bold" fill="#0f766e">80048</text>
      <text x="300" y="475" font-family="Arial" font-size="13" fill="#475569">Metabolic panel (x2)</text>
      <text x="640" y="475" font-family="Arial" font-size="13" fill="#334155" text-anchor="end">$930.00</text>
      <rect x="40" y="1010" width="720" height="60" rx="8" fill="#f0fdfa"/>
      <text x="500" y="1035" font-family="Arial" font-size="14" font-weight="bold" fill="#0f766e" text-anchor="end">TOTAL CHARGES</text>
      <text x="740" y="1055" font-family="Arial" font-size="16" font-weight="bold" fill="#0f766e" text-anchor="end" transform="translate(-20,0)">$7,842.50</text>
    </svg>`
  ), thumbnailUrl: null, width: 800, height: 1100 };

  const PAGE_2 = { index: 2, imageUrl: "data:image/svg+xml," + encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1100">
      <rect width="800" height="1100" fill="#fff"/>
      <rect x="40" y="40" width="720" height="60" rx="8" fill="#f0fdfa"/>
      <text x="60" y="72" font-family="Arial" font-size="16" font-weight="bold" fill="#0d9488">ST. MARY'S MEDICAL CENTER — PAGE 2</text>
      <text x="60" y="130" font-family="Arial" font-size="13" fill="#334155">01/22/26</text>
      <text x="180" y="130" font-family="monospace" font-size="13" font-weight="bold" fill="#0f766e">99221</text>
      <text x="300" y="130" font-family="Arial" font-size="13" fill="#475569">Initial hospital care, low</text>
      <text x="640" y="130" font-family="Arial" font-size="13" fill="#334155" text-anchor="end">$1,040.00</text>
      <text x="60" y="160" font-family="Arial" font-size="13" fill="#334155">01/22/26</text>
      <text x="180" y="160" font-family="monospace" font-size="13" font-weight="bold" fill="#0f766e">J1200</text>
      <text x="300" y="160" font-family="Arial" font-size="13" fill="#475569">Dexamethasone 1mg x12</text>
      <text x="640" y="160" font-family="Arial" font-size="13" fill="#334155" text-anchor="end">$240.00</text>
      <text x="60" y="190" font-family="Arial" font-size="13" fill="#334155">01/22/26</text>
      <text x="180" y="190" font-family="monospace" font-size="13" font-weight="bold" fill="#0f766e">J0202</text>
      <text x="300" y="190" font-family="Arial" font-size="13" fill="#475569">Alteplase, thrombolytic</text>
      <text x="640" y="190" font-family="Arial" font-size="13" fill="#334155" text-anchor="end">$1,870.50</text>
      <text x="60" y="220" font-family="Arial" font-size="13" fill="#334155">01/22/26</text>
      <text x="180" y="220" font-family="monospace" font-size="13" font-weight="bold" fill="#0f766e">A0428</text>
      <text x="300" y="220" font-family="Arial" font-size="13" fill="#475569">Ambulance, BLS</text>
      <text x="640" y="220" font-family="Arial" font-size="13" fill="#334155" text-anchor="end">$837.00</text>
      <text x="540" y="880" font-family="Arial" font-size="14" fill="#475569">VERIFICATION NOTE:</text>
      <text x="540" y="900" font-family="Arial" font-size="12" fill="#94a3b8">Some fields on this page were</text>
      <text x="540" y="918" font-family="Arial" font-size="12" fill="#94a3b8">difficult to read — small print.</text>
    </svg>`
  ), thumbnailUrl: null, width: 800, height: 1100 };

  function buildPages() {
    return [PAGE_1, PAGE_2].map((p) => ({ ...p }));
  }

  /* ----- Line items for the ER bill (ParsedBill shape) ----- */

  function erLineItems() {
    const v = (verified, confidence = 0.98, method = "ocr_high_confidence", note = null) => ({
      verified, confidence: verified ? confidence : null, method: verified ? method : (note ? "manual_review" : "absent"), note: note || null
    });

    return [
      {
        id: "li-1", page: 1, bbox: { page: 1, x: 0.07, y: 0.28, w: 0.8, h: 0.035 },
        serviceDate: "2026-01-22", cptCode: "99283", hcpcsCode: null, code: "99283", codeType: "CPT",
        description: "Emergency department visit, level 3", units: 1, modifiers: [], placeOfService: "23",
        icdCodes: [{ code: "R07.9", description: "Chest pain, unspecified" }],
        amounts: { charge: 1450.0, allowed: 1010.0, paid: 808.0, patientResponsibility: 202.0 },
        verification: {
          amounts: v(true, 0.99), description: v(true, 0.97), code: v(true, 0.99), date: v(true, 0.98)
        }
      },
      {
        id: "li-2", page: 1, bbox: { page: 1, x: 0.07, y: 0.315, w: 0.8, h: 0.035 },
        serviceDate: "2026-01-22", cptCode: "99284", hcpcsCode: null, code: "99284", codeType: "CPT",
        description: "Emergency department visit, level 4 (billed separately from 99283)", units: 1, modifiers: [], placeOfService: "23",
        icdCodes: [{ code: "R07.9", description: "Chest pain, unspecified" }],
        amounts: { charge: 1120.0, allowed: 640.0, paid: 512.0, patientResponsibility: 128.0 },
        verification: {
          amounts: v(true, 0.99), description: v(true, 0.94, "ocr_high_confidence", "Handwritten annotation read with moderate confidence"), code: v(true, 0.97), date: v(false, null, "manual_review", "Date smudged — matched against adjacent lines")
        }
      },
      {
        id: "li-3", page: 1, bbox: { page: 1, x: 0.07, y: 0.35, w: 0.8, h: 0.035 },
        serviceDate: "2026-01-22", cptCode: "99285", hcpcsCode: null, code: "99285", codeType: "CPT",
        description: "Emergency department visit, level 5", units: 1, modifiers: [], placeOfService: "23",
        icdCodes: [{ code: "R07.9", description: "Chest pain, unspecified" }],
        amounts: { charge: 890.0, allowed: 890.0, paid: 0.0, patientResponsibility: 890.0 },
        verification: {
          amounts: v(true, 0.99), description: v(true, 0.96), code: v(true, 0.98), date: v(true, 0.97)
        }
      },
      {
        id: "li-4", page: 1, bbox: { page: 1, x: 0.07, y: 0.385, w: 0.8, h: 0.035 },
        serviceDate: "2026-01-22", cptCode: "93005", hcpcsCode: null, code: "93005", codeType: "CPT",
        description: "Electrocardiogram, routine tracing only", units: 1, modifiers: [], placeOfService: "23",
        icdCodes: [{ code: "R07.9", description: "Chest pain, unspecified" }],
        amounts: { charge: 320.0, allowed: 228.0, paid: 182.4, patientResponsibility: 45.6 },
        verification: {
          amounts: v(true, 0.99), description: v(true, 0.98), code: v(true, 0.99), date: v(true, 0.98)
        }
      },
      {
        id: "li-5", page: 1, bbox: { page: 1, x: 0.07, y: 0.42, w: 0.8, h: 0.035 },
        serviceDate: "2026-01-22", cptCode: "81003", hcpcsCode: null, code: "81003", codeType: "CPT",
        description: "Urinalysis, automated", units: 1, modifiers: [], placeOfService: "23",
        icdCodes: [{ code: "R82.90", description: "Unspecified abnormal urine findings" }],
        amounts: { charge: 145.0, allowed: 92.0, paid: 73.6, patientResponsibility: 18.4 },
        verification: {
          amounts: v(true, 0.99), description: v(true, 0.98), code: v(true, 0.99), date: v(true, 0.98)
        }
      },
      {
        id: "li-6", page: 1, bbox: { page: 1, x: 0.07, y: 0.455, w: 0.8, h: 0.035 },
        serviceDate: "2026-01-22", cptCode: "80048", hcpcsCode: null, code: "80048", codeType: "CPT",
        description: "Basic metabolic panel (qty 2)", units: 2, modifiers: [], placeOfService: "23",
        icdCodes: [{ code: "E11.9", description: "Type 2 diabetes mellitus without complications" }],
        amounts: { charge: 930.0, allowed: 465.0, paid: 372.0, patientResponsibility: 93.0 },
        verification: {
          amounts: v(true, 0.99), description: v(true, 0.97), code: v(true, 0.99), date: v(true, 0.98)
        }
      },
      {
        id: "li-7", page: 2, bbox: { page: 2, x: 0.07, y: 0.10, w: 0.8, h: 0.035 },
        serviceDate: "2026-01-22", cptCode: "99221", hcpcsCode: null, code: "99221", codeType: "CPT",
        description: "Initial hospital inpatient care, low complexity", units: 1, modifiers: [], placeOfService: "21",
        icdCodes: [{ code: "I10", description: "Essential (primary) hypertension" }],
        amounts: { charge: 1040.0, allowed: 760.0, paid: 608.0, patientResponsibility: 152.0 },
        verification: {
          amounts: v(true, 0.98), description: v(true, 0.93, "ocr_high_confidence", "Small print — moderate confidence"), code: v(true, 0.96), date: v(false, null, "manual_review", "Partially clipped in scan")
        }
      },
      {
        id: "li-8", page: 2, bbox: { page: 2, x: 0.07, y: 0.135, w: 0.8, h: 0.035 },
        serviceDate: "2026-01-22", cptCode: null, hcpcsCode: "J1200", code: "J1200", codeType: "HCPCS",
        description: "Dexamethasone sodium phosphate 1mg (12 units)", units: 12, modifiers: ["JB"], placeOfService: "21",
        icdCodes: [{ code: "I10", description: "Essential (primary) hypertension" }],
        amounts: { charge: 240.0, allowed: 186.0, paid: 148.8, patientResponsibility: 37.2 },
        verification: {
          amounts: v(true, 0.99), description: v(true, 0.95), code: v(true, 0.98), date: v(false, null, "manual_review", "Date column partially unreadable on page 2")
        }
      },
      {
        id: "li-9", page: 2, bbox: { page: 2, x: 0.07, y: 0.17, w: 0.8, h: 0.035 },
        serviceDate: "2026-01-22", cptCode: null, hcpcsCode: "J0202", code: "J0202", codeType: "HCPCS",
        description: "Alteplase (tPA), thrombolytic therapy", units: 1, modifiers: [], placeOfService: "21",
        icdCodes: [{ code: "I63.9", description: "Cerebral infarction, unspecified" }],
        amounts: { charge: 1870.5, allowed: 1540.0, paid: 1232.0, patientResponsibility: 308.0 },
        verification: {
          amounts: v(true, 0.99), description: v(true, 0.96), code: v(true, 0.98), date: v(false, null, "manual_review", "Date column partially unreadable on page 2")
        }
      },
      {
        id: "li-10", page: 2, bbox: { page: 2, x: 0.07, y: 0.205, w: 0.8, h: 0.035 },
        serviceDate: "2026-01-22", cptCode: null, hcpcsCode: "A0428", code: "A0428", codeType: "HCPCS",
        description: "Ambulance service, BLS, non-emergency transport", units: 1, modifiers: [], placeOfService: "41",
        icdCodes: [{ code: "R07.9", description: "Chest pain, unspecified" }],
        amounts: { charge: 837.0, allowed: 610.0, paid: 488.0, patientResponsibility: 122.0 },
        verification: {
          amounts: v(true, 0.99), description: v(true, 0.97), code: v(true, 0.98), date: v(false, null, "manual_review", "Date column partially unreadable on page 2")
        }
      }
    ];
  }

  function erTotals() {
    return {
      billed: 7842.5,
      allowed: 6421.0,
      paid: 4424.8,
      patientResponsibility: 1996.2,
      reconciliation: {
        ok: true,
        diff: 0.0,
        note: "Billed = allowed + patient responsibility"
      }
    };
  }

  function erMetadata() {
    return {
      provider: "St. Mary's Medical Center",
      providerNpi: "1834459021",
      payer: "BlueCross Shield TX",
      statementDate: "2026-01-28",
      accountRef: "4821-9930",
      memberName: "Alex Sharma",
      memberId: "X-8842-001",
      patientLiability: 1996.2
    };
  }

  function erExtractionWarnings() {
    return [
      { page: 2, message: "Some fields on page 2 were hard to read — small print in the date column. Please review.", severity: "warning" }
    ];
  }

  /* ----- Flags in FlagSet shape with SHAP payloads ----- */

  function erFlags(complete) {
    return {
      documentId: "doc-er-001",
      flags: [
        {
          id: "flag-1",
          category: "unbundling",
          title: "Unbundled procedure codes",
          severity: "high",
          confidence: 0.94,
          detectionType: "rule",
          flagAmount: 1120.0,
          lineItemIds: ["li-1", "li-2"],
          summary: "CPT 99283 and 99284 billed for the same visit — mutually exclusive codes.",
          description: "Two emergency department codes were billed for a single visit on 01/22/2026. CPT guidelines treat 99283 and 99284 as mutually exclusive for the same encounter; billing both is a frequent unbundling error.",
          why: {
            title: "Why this was flagged",
            contributions: [
              { feature: "mutually_exclusive_pair", label: "Mutually exclusive code pair", value: 1, direction: "up", description: "CPT 99283 and 99284 form a known mutually-exclusive pair for the same date/patient/encounter." },
              { feature: "same_encounter", label: "Same encounter evidence", value: 1, direction: "up", description: "Both codes share the same date of service, place of service (23) and member ID — consistent with one encounter." },
              { feature: "line_item_count", label: "Duplicate-position codes", value: 2, direction: "up", description: "Exactly two ER visit codes present; the lower-complexity code absorbs the higher one." }
            ]
          },
          evidence: { codeReference: "CPT GPT 2026 — 99283 / 99284 mutually exclusive", source: "AMA CPT Rules Engine" }
        },
        {
          id: "flag-2",
          category: "upcoding",
          title: "Possible upcoding — level-5 billed vs level-4 documented",
          severity: "medium",
          confidence: 0.87,
          detectionType: "ml",
          flagAmount: 890.0,
          lineItemIds: ["li-3"],
          summary: "Level-5 ER visit (99285) billed; documentation supports level-4 (99284).",
          description: "A level-5 emergency visit was billed, but the clinical documentation (30-minute visit, no complex medical decision-making) supports only a level-4 code. This is a classic upcoding pattern.",
          why: {
            title: "Why this was flagged",
            contributions: [
              { feature: "cpt_price_ratio", label: "Charge vs regional median", value: 2.1, direction: "up", description: "Charge is 2.1x the regional median for CPT 99285 ($890 vs median $420)." },
              { feature: "documentation_complexity", label: "Documented complexity", value: 0.3, direction: "up", description: "Chart notes show moderate (level-4) rather than high (level-5) medical decision-making." },
              { feature: "visit_duration", label: "Visit duration", value: 30, direction: "down", description: "Typical 99285 visits average 45–60 minutes; a 30-minute visit lowers the posterior probability of a true level-5." },
              { feature: "provider_histogram", label: "Provider coding history", value: 1.8, direction: "up", description: "Provider's level-5 billing rate is 1.8x the peer average, an upcoding-sensitive profile." }
            ]
          },
          evidence: { codeReference: "CMS E/M Documentation Guidelines 2023", source: "Chart-review NLP model v3" }
        },
        {
          id: "flag-3",
          category: "duplicate_charge",
          title: "Duplicate charge — metabolic panel",
          severity: "high",
          confidence: 0.91,
          detectionType: "rule",
          flagAmount: 930.0,
          lineItemIds: ["li-6"],
          summary: "CPT 80048 billed twice (qty 2) on the same date for the same patient.",
          description: "The basic metabolic panel (CPT 80048) appears as qty 2 on the same date of service. A single panel is standard for one encounter; the second unit is a duplicate.",
          why: {
            title: "Why this was flagged",
            contributions: [
              { feature: "same_code_same_date", label: "Same code + same date", value: 1, direction: "up", description: "Two units of 80048 on the same date, same patient, same place of service." },
              { feature: "expected_units", label: "Expected units for panel", value: 1, direction: "up", description: "80048 is a once-per-encounter panel; qty > 1 is abnormal." },
              { feature: "allowed_ratio", label: "Allowed amount ratio", value: 0.5, direction: "up", description: "Allowed amount is exactly half of billed — consistent with two identical units." }
            ]
          },
          evidence: { codeReference: "CPT 80048 — panel, once per encounter", source: "Duplicate-charge rule engine" }
        },
        {
          id: "flag-4",
          category: "pricing_anomaly",
          title: "Pricing anomaly — J0202 alteplase",
          severity: "low",
          confidence: 0.72,
          detectionType: "ml",
          flagAmount: 331.5,
          lineItemIds: ["li-9"],
          summary: "Alteplase charge is 1.84x the regional median for this drug.",
          description: "The billed amount for J0202 (alteplase) is $1,870.50; the regional median for this HCPCS is ~$1,539. The delta of $331.50 is 1.84x the median — above the 90th percentile of similar claims.",
          why: {
            title: "Why this was flagged",
            contributions: [
              { feature: "cpt_price_ratio", label: "Charge vs regional median", value: 1.84, direction: "up", description: "Charge is 1.84x regional median for J0202." },
              { feature: "wholesale_acq_cost", label: "Drug wholesale acquisition cost", value: 0.94, direction: "down", description: "Billed amount is near 0.94x WAC — a mild markup, slightly lowering anomaly score." },
              { feature: "payer_fee_schedule", label: "Payer usual & customary", value: 0.82, direction: "up", description: "Payer's usual-and-customary for this drug is typically ~$1,540." }
            ]
          },
          evidence: { codeReference: "HCPCS J0202 — WAC reference 2026", source: "Pricing atlas v4.2 (regional claims)" }
        }
      ],
      complete,
      summary: complete
        ? {
            totalFlaggedAmount: 3271.5,
            countByCategory: { duplicate_charge: 1, unbundling: 1, arithmetic_mismatch: 0, invalid_deprecated_code: 0, surprise_billing: 0, pricing_anomaly: 1, upcoding: 1, denied_claim: 0, missing_authorization: 0, coverage_gap: 0 },
            ruleCount: 2,
            mlCount: 2
          }
        : {
            totalFlaggedAmount: 2050.0,
            countByCategory: { duplicate_charge: 1, unbundling: 1, arithmetic_mismatch: 0, invalid_deprecated_code: 0, surprise_billing: 0, pricing_anomaly: 0, upcoding: 0, denied_claim: 0, missing_authorization: 0, coverage_gap: 0 },
            ruleCount: 2,
            mlCount: 0
          }
    };
  }

  function erAppealScore(complete, stale) {
    const SCORE = { score: 0.84, lo: 0.76, hi: 0.90, sample: 1240 };
    const base = {
      documentId: "doc-er-001",
      score: SCORE.score,
      calibrated: true,
      modelVersion: "appeal-xgb-v3-cal",
      confidenceInterval: [SCORE.lo, SCORE.hi],
      sampleSize: SCORE.sample,
      calibration: { expectedError: 0.045 },
      basis: "Based on 1,240 similar appeal policies and outcomes in our model, calibrated to your state (TX) and insurer (BlueCross Shield TX).",
      updatedAt: new Date().toISOString(),
      stale,
      factors: [
        { key: "unbundling_pattern", label: "Unbundling correction", impact: 0.14, direction: "up", description: "Mutually-exclusive codes are a high-success, deterministic correction — 78% of similar cases overturned in your state.", actionable: true },
        { key: "duplicate_charge", label: "Duplicate charge removal", impact: 0.08, direction: "up", description: "Identical same-date units are nearly always refunded on request.", actionable: true },
        { key: "upcoding_support", label: "Chart-documented upcoding", impact: 0.06, direction: "up", description: "Level-5 billed vs level-4 documented is a strong, evidence-backed angle.", actionable: true },
        { key: "jurisdiction", label: "Texas external-review climate", impact: 0.01, direction: "up", description: "Texas grants insureds external review rights within 12 months.", actionable: false },
        { key: "payer_claims_history", label: "Payer denial-reversal history", impact: -0.05, direction: "down", description: "BlueCross Shield TX overturns ~38% of internal appeals at first level.", actionable: false },
        { key: "documentation_quality", label: "Charted documentation quality", impact: -0.03, direction: "down", description: "One page has low-confidence OCR — medical records may carry similar legibility risk.", actionable: false }
      ]
    };
    if (!complete) {
      return {
        ...base,
        score: null,
        calibrated: false,
        factors: [],
        basis: "Appeal score pending — ML scoring stage still running.",
        stale: false
      };
    }
    return base;
  }

  /* ----- A clean bill with zero flags (empty-state demo) ----- */

  function cleanBill() {
    const lineItems = [
      { id: "cli-1", page: 1, bbox: { page: 1, x: 0.08, y: 0.28, w: 0.8, h: 0.035 }, serviceDate: "2026-02-10", cptCode: "99213", hcpcsCode: null, code: "99213", codeType: "CPT", description: "Office visit, established patient, level 3", units: 1, modifiers: [], placeOfService: "11", icdCodes: [{ code: "J06.9", description: "Acute upper respiratory infection, unspecified" }], amounts: { charge: 320.0, allowed: 240.0, paid: 192.0, patientResponsibility: 48.0 }, verification: { amounts: { verified: true, confidence: 0.99, method: "ocr_high_confidence", note: null }, description: { verified: true, confidence: 0.98, method: "ocr_high_confidence", note: null }, code: { verified: true, confidence: 0.99, method: "ocr_high_confidence", note: null }, date: { verified: true, confidence: 0.98, method: "ocr_high_confidence", note: null } } },
      { id: "cli-2", page: 1, bbox: { page: 1, x: 0.08, y: 0.32, w: 0.8, h: 0.035 }, serviceDate: "2026-02-10", cptCode: "81002", hcpcsCode: null, code: "81002", codeType: "CPT", description: "Urinalysis, non-automated, without microscopy", units: 1, modifiers: [], placeOfService: "11", icdCodes: [{ code: "J06.9", description: "Acute upper respiratory infection, unspecified" }], amounts: { charge: 88.0, allowed: 62.0, paid: 49.6, patientResponsibility: 12.4 }, verification: { amounts: { verified: true, confidence: 0.99, method: "ocr_high_confidence", note: null }, description: { verified: true, confidence: 0.98, method: "ocr_high_confidence", note: null }, code: { verified: true, confidence: 0.99, method: "ocr_high_confidence", note: null }, date: { verified: true, confidence: 0.98, method: "ocr_high_confidence", note: null } } }
    ];
    return {
      documentId: "doc-clean-001",
      jobId: "job-clean-001",
      metadata: {
        provider: "Northgate Family Clinic", providerNpi: "1887745520", payer: "UnitedHealth PPO",
        statementDate: "2026-02-15", accountRef: "7311-204", memberName: "Alex Sharma", memberId: "X-8842-001",
        patientLiability: 60.4
      },
      totals: {
        billed: 408.0, allowed: 302.0, paid: 241.6, patientResponsibility: 60.4,
        reconciliation: { ok: true, diff: 0, note: "Billed = allowed + patient responsibility" }
      },
      lineItems,
      pages: [PAGE_1].map((p) => ({ ...p, index: 1, imageUrl: p.imageUrl })),
      extractionWarnings: [],
      extractionStatus: "complete"
    };
  }

  /* ==========================================================
     3. CODE REFERENCE DATA (glossary backing)
     ========================================================== */

  const CODE_REFERENCE = [
    { code: "99283", type: "CPT", description: "Emergency department visit, level 3", plainLanguage: "A moderate-complexity ER visit — usually a single complaint that needs evaluation and some testing.", category: "E/M", aka: null, notes: "Requires a medical decision-making (MDM) level of 'moderate'.", source: "AMA-CPT-2026", deprecated: false, supersededBy: null },
    { code: "99284", type: "CPT", description: "Emergency department visit, level 4", plainLanguage: "A high-complexity ER visit — often multiple complaints or a serious condition requiring extensive testing and treatment decisions.", category: "E/M", aka: null, notes: "Requires 'high' MDM. Do not bill with 99283 for the same encounter.", source: "AMA-CPT-2026", deprecated: false, supersededBy: null },
    { code: "99285", type: "CPT", description: "Emergency department visit, level 5", plainLanguage: "The highest-complexity ER visit — a life- or limb-threatening condition requiring comprehensive assessment and high medical decision-making.", category: "E/M", aka: null, notes: "Requires 'high' MDM and usually 45+ minutes of documented care.", source: "AMA-CPT-2026", deprecated: false, supersededBy: null },
    { code: "99213", type: "CPT", description: "Office visit, established patient, level 3", plainLanguage: "A typical follow-up office visit with moderate issues — one or two stable problems, a prescription refill, or a minor test.", category: "E/M", aka: null, notes: null, source: "AMA-CPT-2026", deprecated: false, supersededBy: null },
    { code: "99214", type: "CPT", description: "Office visit, established patient, level 4", plainLanguage: "A more complex office visit — often one acute problem plus a chronic condition, requiring more detailed review and decision-making.", category: "E/M", aka: null, notes: null, source: "AMA-CPT-2026", deprecated: false, supersededBy: null },
    { code: "93005", type: "CPT", description: "Electrocardiogram, routine tracing only", plainLanguage: "A standard EKG tracing — the graph of your heart's electrical activity, without physician interpretation.", category: "Diagnostics", aka: "ECG / EKG", notes: null, source: "AMA-CPT-2026", deprecated: false, supersededBy: null },
    { code: "80048", type: "CPT", description: "Basic metabolic panel (BMP)", plainLanguage: "A set of 8 common blood-chemistry tests (glucose, calcium, electrolytes, kidney function). Drawn once per encounter.", category: "Lab", aka: null, notes: "Panel — billed once per encounter, not per tube.", source: "AMA-CPT-2026", deprecated: false, supersededBy: null },
    { code: "81002", type: "CPT", description: "Urinalysis, non-automated, without microscopy", plainLanguage: "A routine urine test done manually, checking for infection markers, blood, or protein.", category: "Lab", aka: null, notes: null, source: "AMA-CPT-2026", deprecated: false, supersededBy: null },
    { code: "81003", type: "CPT", description: "Urinalysis, automated, without microscopy", plainLanguage: "A routine urine test run on an automated analyzer, checking for infection markers, blood, or protein.", category: "Lab", aka: null, notes: null, source: "AMA-CPT-2026", deprecated: false, supersededBy: null },
    { code: "29881", type: "CPT", description: "Arthroscopy, knee, medial meniscectomy", plainLanguage: "Keyhole knee surgery to remove a torn piece of the shock-absorbing cartilage (meniscus).", category: "Surgery", aka: "Knee scope", notes: null, source: "AMA-CPT-2026", deprecated: false, supersededBy: null },
    { code: "73562", type: "CPT", description: "Radiologic examination, knee, 3 views", plainLanguage: "Three X-ray views of the knee to check for fractures, arthritis, or alignment issues.", category: "Imaging", aka: null, notes: null, source: "AMA-CPT-2026", deprecated: false, supersededBy: null },
    { code: "99221", type: "CPT", description: "Initial hospital inpatient care, low complexity", plainLanguage: "The first day of a hospital stay, with straightforward care needs.", category: "E/M", aka: null, notes: null, source: "AMA-CPT-2026", deprecated: false, supersededBy: null },
    { code: "J1200", type: "HCPCS", description: "Dexamethasone sodium phosphate 1mg", plainLanguage: "An anti-inflammatory steroid injection, commonly used to reduce swelling.", category: "Drug", aka: "Decadron", notes: "Billed per unit (mg).", source: "CMS-HCPCS-2026", deprecated: false, supersededBy: null },
    { code: "J0202", type: "HCPCS", description: "Alteplase (tPA) injection", plainLanguage: "A clot-busting drug given during a stroke or blood-clot emergency.", category: "Drug", aka: "Activase", notes: "High-cost injectable — verify the charge against WAC.", source: "CMS-HCPCS-2026", deprecated: false, supersededBy: null },
    { code: "J7326", type: "HCPCS", description: "Hyaluronan injection, knee", plainLanguage: "A joint-lubricant injection for knee arthritis ('gel shots').", category: "Drug", aka: "Synvisc / gel shot", notes: null, source: "CMS-HCPCS-2026", deprecated: false, supersededBy: null },
    { code: "A0428", type: "HCPCS", description: "Ambulance service, BLS, non-emergency", plainLanguage: "Basic-life-support ambulance transport when the patient is stable enough not to need ALS.", category: "Transport", aka: null, notes: null, source: "CMS-HCPCS-2026", deprecated: false, supersededBy: null },
    { code: "A4550", type: "HCPCS", description: "Surgical tray", plainLanguage: "The sterile supplies used during a procedure — drapes, gloves, small instruments.", category: "Supply", aka: null, notes: "Watch for inflation — fair median is ~$340.", source: "CMS-HCPCS-2026", deprecated: false, supersededBy: null },
    { code: "G0463", type: "HCPCS", description: "Hospital outpatient clinic visit", plainLanguage: "An outpatient clinic visit at a hospital campus — the facility-side charge for seeing a physician.", category: "Facility", aka: null, notes: null, source: "CMS-HCPCS-2026", deprecated: false, supersededBy: null },
    { code: "R07.9", type: "ICD-10", description: "Chest pain, unspecified", plainLanguage: "A diagnosis code for chest pain when the exact cause isn't yet determined.", category: "Diagnosis", aka: null, notes: null, source: "CMS-ICD10-2026", deprecated: false, supersededBy: null },
    { code: "R82.90", type: "ICD-10", description: "Unspecified abnormal urine findings", plainLanguage: "A diagnosis code for abnormal urine test results that need further investigation.", category: "Diagnosis", aka: null, notes: null, source: "CMS-ICD10-2026", deprecated: false, supersededBy: null },
    { code: "E11.9", type: "ICD-10", description: "Type 2 diabetes mellitus without complications", plainLanguage: "A diagnosis code for type 2 diabetes that isn't currently causing complications.", category: "Diagnosis", aka: null, notes: null, source: "CMS-ICD10-2026", deprecated: false, supersededBy: null },
    { code: "I10", type: "ICD-10", description: "Essential (primary) hypertension", plainLanguage: "A diagnosis code for high blood pressure with no identified secondary cause.", category: "Diagnosis", aka: null, notes: null, source: "CMS-ICD10-2026", deprecated: false, supersededBy: null },
    { code: "I63.9", type: "ICD-10", description: "Cerebral infarction, unspecified", plainLanguage: "A diagnosis code for a stroke caused by a blocked blood vessel.", category: "Diagnosis", aka: null, notes: null, source: "CMS-ICD10-2026", deprecated: false, supersededBy: null },
    { code: "J06.9", type: "ICD-10", description: "Acute upper respiratory infection, unspecified", plainLanguage: "A diagnosis code for a common cold or mild upper-airway infection.", category: "Diagnosis", aka: null, notes: null, source: "CMS-ICD10-2026", deprecated: false, supersededBy: null },
    { code: "Upcoding", type: "Term", description: "Billing a more expensive code than the care documented", plainLanguage: "When a provider bills a higher-level code than the care actually delivered, raising your bill and waste in the system.", category: "Billing terms", aka: null, notes: null, source: "Vitta billing glossary", deprecated: false, supersededBy: null },
    { code: "Unbundling", type: "Term", description: "Billing separate codes that should be billed as one", plainLanguage: "When a provider splits one procedure into multiple codes that shouldn't be billed separately, inflating the total.", category: "Billing terms", aka: null, notes: null, source: "Vitta billing glossary", deprecated: false, supersededBy: null },
    { code: "Balance billing", type: "Term", description: "Billing the patient for the difference between charge and allowed", plainLanguage: "Billing you for the gap between what the provider charged and what insurance paid — often illegal for in-network care.", category: "Billing terms", aka: null, notes: null, source: "Vitta billing glossary", deprecated: false, supersededBy: null },
    { code: "EOB", type: "Term", description: "Explanation of Benefits", plainLanguage: "The statement from your insurer showing what was billed, what was covered, and what you owe.", category: "Billing terms", aka: null, notes: null, source: "Vitta billing glossary", deprecated: false, supersededBy: null },
    { code: "Deductible", type: "Term", description: "Annual out-of-pocket amount before coverage starts", plainLanguage: "The amount you pay each year before your insurance starts sharing costs.", category: "Coverage", aka: null, notes: null, source: "Vitta billing glossary", deprecated: false, supersededBy: null },
    { code: "Coinsurance", type: "Term", description: "Percentage share of covered costs after deductible", plainLanguage: "Your percentage of a covered service after you've met your deductible, e.g. 20% of allowed.", category: "Coverage", aka: null, notes: null, source: "Vitta billing glossary", deprecated: false, supersededBy: null },
    { code: "Copay", type: "Term", description: "Fixed amount paid per covered service", plainLanguage: "A flat fee you pay for a service, like $25 for an office visit.", category: "Coverage", aka: null, notes: null, source: "Vitta billing glossary", deprecated: false, supersededBy: null },
    { code: "No Surprises Act", type: "Term", description: "Federal law protecting against surprise out-of-network bills", plainLanguage: "A law that protects you from most surprise out-of-network bills for emergency care and care at in-network facilities.", category: "Regulation", aka: null, notes: null, source: "CMS — No Surprises Act 2022", deprecated: false, supersededBy: null }
  ];

  /* ==========================================================
     4. MOCK API IMPLEMENTATION
     ========================================================== */

  const STAGE_SEQUENCE = [
    { name: "preprocessing", label: "Preprocessing (deskew, denoise, contrast)", weight: 10, duration: [900, 1500] },
    { name: "ocr_running", label: "OCR running", weight: 25, duration: [1400, 2200] },
    { name: "extraction_running", label: "Extraction running", weight: 25, duration: [1200, 1900] },
    { name: "validation_running", label: "Validation running", weight: 15, duration: [900, 1400] },
    { name: "ml_scoring_running", label: "ML scoring running", weight: 25, duration: [1100, 1700] }
  ];

  const FAILURE_SCENARIOS = {
    ocr_failed: {
      failStage: "ocr_running",
      failure: { code: "OCR_FAILED", message: "The OCR service returned an error while processing page 2. Please retry or re-scan the document." }
    },
    illegible: {
      failStage: "preprocessing",
      failure: { code: "ILLEGIBLE_DOCUMENT", message: "We couldn't read this document — the image is too blurry or dark after enhancement. Try a clearer photo or a higher-resolution scan." }
    },
    unsupported_type: {
      failAtUpload: true,
      failure: { code: "UNSUPPORTED_FILE_TYPE", message: "This file type isn't supported. Upload a PDF, JPG, PNG, or a photo taken with your camera." }
    },
    page_limit: {
      failAtUpload: true,
      failure: { code: "PAGE_LIMIT_EXCEEDED", message: "This document has 15 pages — the current limit is 10 pages per bill. Please split the bill or contact support." }
    }
  };

  class MockVittaAPI {
    constructor(options) {
      this.options = options || {};
      this.baseUrl = this.options.baseUrl || "/api/v1";
      this.listeners = new Map(); // jobId → Set of callbacks
      this._jobs = new Map();
      this._billCache = new Map();
      this._jobSeq = 0;
    }

    /* ---------------- Upload ---------------- */

    /**
     * POST /upload
     * @param {File} file
     * @returns {Promise<UploadResponse>}
     */
    upload(file) {
      const scenario = this._pickScenario(file);
      if (scenario && scenario.failAtUpload) {
        return Promise.reject({ code: scenario.failure.code, message: scenario.failure.message });
      }

      this._jobSeq += 1;
      const jobId = "job-" + String(this._jobSeq).padStart(4, "0") + "-" + Date.now().toString(36);
      const documentId = "doc-" + jobId;
      const isClean = file && (file.name || "").toLowerCase().includes("clean");

      const job = {
        jobId,
        documentId,
        status: "uploading",
        progress: 5,
        stages: [],
        partial: false,
        partialBill: null,
        partialFlags: null,
        partialScore: null,
        extractionWarnings: [],
        _pending: {
          filename: file ? file.name : "sample-bill.pdf",
          isClean: !!isClean,
          scenario: scenario || null,
          timers: []
        },
        _started: false,
        _finished: false
      };
      this._jobs.set(jobId, job);

      // Simulate upload completing
      job._pending.timers.push(setTimeout(() => {
        job.status = "preprocessing";
        job.progress = 8;
        this._emit(job);
        this._runStages(job);
      }, 350));

      const resp = { jobId, documentId, status: "uploading", filename: file ? file.name : (isClean ? "clean-bill.pdf" : "sample-bill.pdf") };

      // Small timeout so the caller sees the initial "uploading" state
      return new Promise((resolve) => setTimeout(() => resolve(resp), 120));
    }

    _pickScenario(file) {
      if (!file) return null;
      const name = (file.name || "").toLowerCase();
      if (name.includes("ocr_failed") || name.includes("ocr-failed")) return FAILURE_SCENARIOS.ocr_failed;
      if (name.includes("illegible") || name.includes("blurry") || name.includes("dark")) return FAILURE_SCENARIOS.illegible;
      if (name.includes("unsupported") || name.includes(".txt")) return FAILURE_SCENARIOS.unsupported_type;
      if (name.includes("long") || name.includes("multi")) return FAILURE_SCENARIOS.page_limit;
      return null;
    }

    /* ---------------- Pipeline job status ---------------- */

    /**
     * GET /jobs/{id}/status
     * @param {string} jobId
     * @returns {Promise<PipelineStatus>}
     */
    getJobStatus(jobId) {
      const job = this._jobs.get(jobId);
      if (!job) return Promise.reject({ code: "NOT_FOUND", message: "Job not found." });
      return Promise.resolve(this._publicStatus(job));
    }

    /**
     * Subscribe to job updates — mirror of a WebSocket channel.
     * Real backend: WS /ws/jobs/{id}. This mock polls getJobStatus
     * and dispatches the same event shape the websocket would.
     * @param {string} jobId
     * @param {(update: PipelineStatus) => void} cb
     * @returns {() => void} unsubscribe
     */
    onJobUpdate(jobId, cb) {
      if (!this.listeners.has(jobId)) this.listeners.set(jobId, new Set());
      this.listeners.get(jobId).add(cb);
      // start polling
      const poll = () => {
        const job = this._jobs.get(jobId);
        if (!job) return;
        cb(this._publicStatus(job));
        if (!job._finished) {
          setTimeout(poll, 700);
        }
      };
      setTimeout(poll, 250);
      return () => {
        const s = this.listeners.get(jobId);
        if (s) s.delete(cb);
      };
    }

    _emit(job) {
      const cbs = this.listeners.get(job.jobId);
      if (cbs) {
        const snap = this._publicStatus(job);
        cbs.forEach((cb) => cb(snap));
      }
    }

    _publicStatus(job) {
      return {
        jobId: job.jobId,
        documentId: job.documentId,
        status: job.status,
        progress: Math.round(job.progress),
        stages: (job.stages || []).map((s) => ({ ...s })),
        failure: job.failure || null,
        partial: !!job.partial,
        partialBill: job.partialBill,
        partialFlags: job.partialFlags,
        partialScore: job.partialScore,
        extractionWarnings: (job.extractionWarnings || []).map((w) => ({ ...w }))
      };
    }

    /* ---------------- Stage runner ---------------- */

    _runStages(job) {
      const seq = STAGE_SEQUENCE.map((s) => ({ ...s }));
      // If failure scenario targets a stage, we still process prior stages
      const failStageName = job._pending.scenario ? job._pending.scenario.failStage : null;

      let idx = 0;
      const runNext = () => {
        if (job._finished) return;
        if (idx >= seq.length) {
          this._finishJob(job);
          return;
        }
        const stageDef = seq[idx];
        idx += 1;

        const stage = {
          name: stageDef.name,
          status: "running",
          startedAt: new Date().toISOString(),
          completedAt: null,
          error: null,
          errorCode: null
        };
        job.stages.push(stage);
        job.status = stageDef.name;
        // progress: move from prior stage end toward this stage's end
        const priorEnd = idx === 1 ? 8 : STAGE_SEQUENCE.slice(0, idx - 1).reduce((acc, s) => acc + s.weight, 8);
        const thisEnd = STAGE_SEQUENCE.slice(0, idx).reduce((acc, s) => acc + s.weight, 8);
        job.progress = Math.min(thisEnd, priorEnd + 2);
        this._emit(job);

        // Simulate stage work
        const [dMin, dMax] = stageDef.duration;
        const dur = rand(dMin, dMax);

        job._pending.timers.push(setTimeout(() => {
          // Failure scenario?
          if (job._pending.scenario && failStageName === stageDef.name) {
            stage.status = "failed";
            stage.error = job._pending.scenario.failure.message;
            stage.errorCode = job._pending.scenario.failure.code;
            stage.completedAt = new Date().toISOString();
            job.status = "failed";
            job.failure = job._pending.scenario.failure;
            job._finished = true;
            this._emit(job);
            this._cleanupTimers(job);
            return;
          }

          stage.status = "done";
          stage.completedAt = new Date().toISOString();
          job.progress = thisEnd;

          // Populate partial results as stages complete
          if (stageDef.name === "ocr_running") {
            // Pages become available
            const bill = job._pending.isClean ? cleanBill() : this._buildBill(job.documentId);
            job._currentBill = bill;
            job.partial = true;
            job.partialBill = {
              ...bill,
              lineItems: [],
              extractionStatus: "partial"
            };
            job.extractionWarnings = bill.extractionWarnings;
          }
          if (stageDef.name === "extraction_running") {
            job.partial = true;
            job.partialBill = job._currentBill; // full bill now
          }
          if (stageDef.name === "validation_running") {
            job.partial = true;
            const flags = job._pending.isClean ? { documentId: job.documentId, flags: [], complete: false, summary: { totalFlaggedAmount: 0, countByCategory: {}, ruleCount: 0, mlCount: 0 } } : erFlags(false);
            job.partialFlags = flags;
          }
          if (stageDef.name === "ml_scoring_running") {
            job.partial = true;
            if (!job._pending.isClean) {
              job.partialScore = erAppealScore(false, false);
            }
          }

          this._emit(job);

          // stagger to simulate work in progress
          job._pending.timers.push(setTimeout(runNext, rand(150, 400)));
        }, dur));
      };

      runNext();
    }

    _finishJob(job) {
      job.status = "done";
      job.progress = 100;
      job.partial = true;
      if (!job._pending.isClean) {
        job.partialFlags = erFlags(true);
        job.partialScore = erAppealScore(true, false);
      } else {
        job.partialFlags = { documentId: job.documentId, flags: [], complete: true, summary: { totalFlaggedAmount: 0, countByCategory: {}, ruleCount: 0, mlCount: 0 } };
        job.partialScore = {
          documentId: job.documentId, score: 0.91, calibrated: true, modelVersion: "appeal-xgb-v3-cal",
          confidenceInterval: [0.84, 0.95], sampleSize: 980, calibration: { expectedError: 0.04 },
          basis: "Based on 980 similar single-visit claims in our model. A clean bill with no flags typically has a high appeal-policy match confidence.",
          updatedAt: new Date().toISOString(), stale: false,
          factors: [
            { key: "no_flags", label: "No billing errors detected", impact: 0.02, direction: "up", description: "The bill matches expected coding and pricing patterns for this service.", actionable: false },
            { key: "coverage_confidence", label: "In-network coverage match", impact: 0.05, direction: "up", description: "Your plan covers this service; standard cost-sharing applies.", actionable: false }
          ]
        };
      }
      job._finished = true;
      this._emit(job);
      this._cleanupTimers(job);
    }

    _cleanupTimers(job) {
      (job._pending.timers || []).forEach((t) => clearTimeout(t));
      job._pending.timers = [];
    }

    _buildBill(documentId) {
      return {
        documentId,
        jobId: documentId.replace("doc-", "job-"),
        metadata: erMetadata(),
        totals: erTotals(),
        lineItems: erLineItems(),
        pages: buildPages(),
        extractionWarnings: erExtractionWarnings(),
        extractionStatus: "complete"
      };
    }

    /* ---------------- Bill retrieval ---------------- */

    /**
     * GET /bills/{id}
     * @param {string} documentId
     * @returns {Promise<ParsedBill>}
     */
    getBill(documentId) {
      if (documentId && documentId.includes("clean")) return Promise.resolve(cleanBill());
      const bill = this._billCache.get(documentId) || this._buildBill(documentId);
      this._billCache.set(documentId, bill);
      return new Promise((resolve) => setTimeout(() => resolve(bill), 200));
    }

    /* ---------------- Flags ---------------- */

    /**
     * GET /bills/{id}/flags
     * @param {string} documentId
     * @returns {Promise<FlagSet>}
     */
    getFlags(documentId) {
      if (documentId && documentId.includes("clean")) {
        return Promise.resolve({ documentId, flags: [], complete: true, summary: { totalFlaggedAmount: 0, countByCategory: {}, ruleCount: 0, mlCount: 0 } });
      }
      return new Promise((resolve) => setTimeout(() => resolve(erFlags(true)), 180));
    }

    /* ---------------- Appeal score ---------------- */

    /**
     * GET /bills/{id}/appeal-score
     * @param {string} documentId
     * @returns {Promise<AppealScore>}
     */
    getAppealScore(documentId) {
      if (documentId && documentId.includes("clean")) {
        return Promise.resolve({
          documentId, score: 0.91, calibrated: true, modelVersion: "appeal-xgb-v3-cal",
          confidenceInterval: [0.84, 0.95], sampleSize: 980, calibration: { expectedError: 0.04 },
          basis: "Based on 980 similar single-visit claims in our model.",
          updatedAt: new Date().toISOString(), stale: false,
          factors: [
            { key: "no_flags", label: "No billing errors detected", impact: 0.02, direction: "up", description: "The bill matches expected coding and pricing patterns for this service.", actionable: false },
            { key: "coverage_confidence", label: "In-network coverage match", impact: 0.05, direction: "up", description: "Your plan covers this service; standard cost-sharing applies.", actionable: false }
          ]
        });
      }
      return new Promise((resolve) => setTimeout(() => resolve(erAppealScore(true, false)), 180));
    }

    /**
     * POST /bills/{id}/appeal-score/recompute
     * Hook for "score recomputes if the user edits the appeal letter or claim details".
     * @param {string} documentId
     * @param {Object} inputs — edited letter/claim deltas
     * @returns {Promise<AppealScore>}
     */
    recomputeAppealScore(documentId, inputs) {
      const base = erAppealScore(true, false);
      base.score = Math.max(0.15, Math.min(0.97, base.score + (inputs && inputs.adjustment || 0)));
      base.updatedAt = new Date().toISOString();
      base.stale = false;
      base.basis = "Recomputed after your edits. Based on 1,240 similar appeal policies and outcomes in our model.";
      return new Promise((resolve) => setTimeout(() => resolve(base), 600));
    }

    /* ---------------- Code glossary ---------------- */

    /**
     * GET /codes/{code}
     * @param {string} code
     * @returns {Promise<CodeDefinition>}
     */
    getCode(code) {
      const key = String(code || "").trim().toUpperCase();
      const found = CODE_REFERENCE.find((c) => c.code.toUpperCase() === key);
      if (!found) {
        return Promise.reject({ code: "NOT_FOUND", message: "Code " + code + " not found in reference data." });
      }
      return new Promise((resolve) => setTimeout(() => resolve({ ...found }), 60));
    }

    /**
     * GET /codes?q=...
     * @param {string} q
     * @returns {Promise<CodeDefinition[]>}
     */
    searchCodes(q) {
      const query = String(q || "").toLowerCase();
      const items = CODE_REFERENCE.filter(
        (c) => !query || c.code.toLowerCase().includes(query) || c.description.toLowerCase().includes(query) || c.plainLanguage.toLowerCase().includes(query) || c.type.toLowerCase().includes(query)
      );
      return new Promise((resolve) => setTimeout(() => resolve(items.map((c) => ({ ...c }))), 60));
    }
  }

  /* ==========================================================
     4b. REAL HTTP CLIENT — implements the same contract
     ========================================================== */

  class HttpClientVittaAPI {
    constructor(options) {
      this.options = options || {};
      this.baseUrl = (this.options.baseUrl || "/api/v1").replace(/\/+$/, "");
      this.authToken = this.options.authToken || null;
      this.wsBaseUrl = this.options.wsBaseUrl || this._deriveWsUrl(this.baseUrl);
      this._pollers = new Map();
    }

    _deriveWsUrl(baseUrl) {
      return baseUrl.replace(/^http/, "ws") + "/ws";
    }

    _headers(extra) {
      const h = Object.assign({ "Content-Type": "application/json" }, extra || {});
      if (this.authToken) h["Authorization"] = "Bearer " + this.authToken;
      return h;
    }

    async _request(path, options) {
      const url = this.baseUrl + path;
      let resp;
      try {
        resp = await fetch(url, options);
      } catch (err) {
        throw { code: "NETWORK", message: "Could not reach the pipeline service. Please check your connection and try again." };
      }
      if (!resp.ok) {
        let err;
        try { err = await resp.json(); } catch (e) { err = {}; }
        throw {
          code: err.code || "HTTP_" + resp.status,
          message: err.message || "Request failed with status " + resp.status,
          status: resp.status
        };
      }
      return resp.json();
    }

    /**
     * POST /upload — multipart/form-data with the file.
     * @param {File} file
     * @returns {Promise<UploadResponse>}
     */
    async upload(file) {
      const form = new FormData();
      form.append("file", file);
      const headers = {};
      if (this.authToken) headers["Authorization"] = "Bearer " + this.authToken;
      let resp;
      try {
        resp = await fetch(this.baseUrl + "/upload", { method: "POST", body: form, headers });
      } catch (err) {
        throw { code: "NETWORK", message: "Could not reach the pipeline service. Please check your connection and try again." };
      }
      if (!resp.ok) {
        let err;
        try { err = await resp.json(); } catch (e) { err = {}; }
        throw { code: err.code || "UPLOAD_FAILED", message: err.message || "Upload failed with status " + resp.status };
      }
      return resp.json();
    }

    /**
     * GET /jobs/{id}/status
     * @param {string} jobId
     * @returns {Promise<PipelineStatus>}
     */
    async getJobStatus(jobId) {
      return this._request("/jobs/" + encodeURIComponent(jobId) + "/status");
    }

    /**
     * Subscribe to job updates — real backend uses WS /ws/jobs/{id}.
     * Falls back to polling if WebSocket is unavailable or errors.
     * @param {string} jobId
     * @param {(update: PipelineStatus) => void} cb
     * @returns {() => void} unsubscribe
     */
    onJobUpdate(jobId, cb) {
      if (typeof WebSocket !== "undefined") {
        try {
          const ws = new WebSocket(this.wsBaseUrl + "/jobs/" + encodeURIComponent(jobId));
          let closed = false;
          ws.onmessage = (e) => {
            try { cb(JSON.parse(e.data)); } catch (err) { /* ignore malformed frames */ }
          };
          ws.onerror = () => {
            if (!closed) { closed = true; try { ws.close(); } catch (e) {} this._pollJob(jobId, cb); }
          };
          ws.onclose = () => {
            if (!closed) { closed = true; this._pollJob(jobId, cb); }
          };
          return () => { closed = true; try { ws.close(); } catch (e) {} };
        } catch (err) {
          // WebSocket constructor threw — fall back to polling
        }
      }
      return this._pollJob(jobId, cb);
    }

    _pollJob(jobId, cb) {
      if (this._pollers.has(jobId)) return this._pollers.get(jobId);
      let stopped = false;
      let timer = null;
      const poll = async () => {
        if (stopped) return;
        try {
          const status = await this.getJobStatus(jobId);
          cb(status);
          if (status.status !== "done" && status.status !== "failed") {
            timer = setTimeout(poll, 1000);
          }
        } catch (err) {
          timer = setTimeout(poll, 2000);
        }
      };
      poll();
      const stop = () => { stopped = true; if (timer) clearTimeout(timer); this._pollers.delete(jobId); };
      this._pollers.set(jobId, stop);
      return stop;
    }

    /**
     * GET /bills/{id}
     * @param {string} documentId
     * @returns {Promise<ParsedBill>}
     */
    async getBill(documentId) {
      return this._request("/bills/" + encodeURIComponent(documentId));
    }

    /**
     * GET /bills/{id}/flags
     * @param {string} documentId
     * @returns {Promise<FlagSet>}
     */
    async getFlags(documentId) {
      return this._request("/bills/" + encodeURIComponent(documentId) + "/flags");
    }

    /**
     * GET /bills/{id}/appeal-score
     * @param {string} documentId
     * @returns {Promise<AppealScore>}
     */
    async getAppealScore(documentId) {
      return this._request("/bills/" + encodeURIComponent(documentId) + "/appeal-score");
    }

    /**
     * POST /bills/{id}/appeal-score/recompute
     * @param {string} documentId
     * @param {Object} inputs — edited letter/claim deltas
     * @returns {Promise<AppealScore>}
     */
    async recomputeAppealScore(documentId, inputs) {
      return this._request("/bills/" + encodeURIComponent(documentId) + "/appeal-score/recompute", {
        method: "POST",
        headers: this._headers(),
        body: JSON.stringify(inputs || {})
      });
    }

    /**
     * GET /codes/{code}
     * @param {string} code
     * @returns {Promise<CodeDefinition>}
     */
    async getCode(code) {
      return this._request("/codes/" + encodeURIComponent(code));
    }

    /**
     * GET /codes?q=...
     * @param {string} q
     * @returns {Promise<CodeDefinition[]>}
     */
    async searchCodes(q) {
      return this._request("/codes?q=" + encodeURIComponent(q || ""));
    }
  }

  /* ==========================================================
     5. EXPORT
     ========================================================== */

  /**
   * Create an API client.
   * Mode resolution order:
   *   1. options.mode ("mock" | "real")
   *   2. window.VITTA_API_MODE (set before this script loads)
   *   3. ?api=real|mock URL parameter
   *   4. default "mock"
   */
  global.VittaAPI = {
    create: (options) => {
      const opts = options || {};
      const urlMode = new URLSearchParams(window.location.search).get("api");
      const mode = opts.mode || global.VITTA_API_MODE || urlMode || "mock";
      if (mode === "real") return new HttpClientVittaAPI(opts);
      return new MockVittaAPI(opts);
    },
    CODE_REFERENCE,
    FAILURE_SCENARIOS,
    HttpClientVittaAPI,
    MockVittaAPI
  };
})(window);
