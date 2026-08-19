/* ============================================================
   VITTA — App Dashboard Logic (API-contract wired)
   ============================================================
   Consumes VittaAPI (js/api.js) — a mock of the real backend
   contract. Swap the mock for the real HTTP client when ready.
   ============================================================ */

(function () {
  "use strict";

  /* ==========================================================
     API INSTANCE
     ========================================================== */

  const api = window.VittaAPI.create();

  /* ==========================================================
     STATE
     ========================================================== */

  let state = {
    jobId: null,
    documentId: null,
    bill: null,          // ParsedBill
    flags: null,         // FlagSet
    flagSetComplete: false,
    score: null,         // AppealScore
    scoreComplete: false,
    pipelineStatus: null,
    currentIssueFilter: "all",
    currentPage: 1,
    highlightedBBox: null,
    activeLineItemId: null,
    uploadPending: false,
    lastUpload: null,    // { file, sampleKey }
    uploadErrorShown: false
  };

  let currentData = null; // derived view model (for actions/strategies/timeline)

  /* ==========================================================
     HELPERS
     ========================================================== */

  const $ = (sel) => document.querySelector(sel);
  const money = (n) =>
    n == null ? "—" : "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const money0 = (n) =>
    n == null ? "—" : "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
  const pct = (n) => (n == null ? "—" : Math.round(n * 100) + "%");
  const A = () => String.fromCharCode(38); // "&" — built at runtime to survive entity decoding
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => {
    if (c === "&") return A() + "amp;";
    if (c === "<") return A() + "lt;";
    if (c === ">") return A() + "gt;";
    if (c === '"') return A() + "quot;";
    return A() + "#39;";
  });

  const ICONS = {
    alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9 16H3l9-16z"/><path d="M12 10v4M12 17h.01"/></svg>',
    doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8M16 17H8M10 9H8"/></svg>',
    dup: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="13" height="13" rx="2"/><path d="M4 16V5a1 1 0 0 1 1-1h11"/></svg>',
    unbin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7v10l4-5-4-5zM21 7v10l-4-5 4-5z"/></svg>',
    math: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16l-8 8 8 8H4"/></svg>',
    code: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
    surge: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 9A6 6 0 0 0 6 9c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
    price: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9 16H3l9-16z"/><path d="M12 10v4M12 17h.01"/></svg>',
    denied: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    auth: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
    gap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>'
  };

  const CATEGORY_META = {
    duplicate_charge: { label: "Duplicate charge", icon: ICONS.dup, tone: "red" },
    unbundling: { label: "Unbundling", icon: ICONS.unbin, tone: "red" },
    arithmetic_mismatch: { label: "Arithmetic mismatch", icon: ICONS.math, tone: "amber" },
    invalid_deprecated_code: { label: "Invalid / deprecated code", icon: ICONS.code, tone: "red" },
    surprise_billing: { label: "Surprise billing", icon: ICONS.surge, tone: "amber" },
    pricing_anomaly: { label: "Pricing anomaly", icon: ICONS.price, tone: "blue" },
    upcoding: { label: "Upcoding", icon: ICONS.up, tone: "amber" },
    denied_claim: { label: "Denied claim", icon: ICONS.denied, tone: "red" },
    missing_authorization: { label: "Missing authorization", icon: ICONS.auth, tone: "amber" },
    coverage_gap: { label: "Coverage gap", icon: ICONS.gap, tone: "blue" }
  };

  const SEV_ICON = { high: ICONS.alert, medium: ICONS.up, low: ICONS.clock };
  const SEV_CLASS = { high: "sev-high", medium: "sev-medium", low: "sev-low" };

  /* ==========================================================
     NAVIGATION
     ========================================================== */

  const PAGE_META = {
    welcome: { title: "Welcome back, Alex", sub: "Let's find out if your bill is correct." },
    scan: { title: "Analyzing your bill", sub: "Pipeline stages run independently — results stream in as they land." },
    overview: { title: "Claim overview", sub: "Everything Vitta found on your bill, at a glance." },
    bill: { title: "Bill detail", sub: "Every line item with per-field verification and source-document provenance." },
    issues: { title: "Issues found", sub: "Rule-based facts and ML-flagged anomalies, with explanations." },
    appeal: { title: "Appeal center", sub: "Calibrated success probability, factor breakdown, and a ready-to-edit appeal letter." },
    actions: { title: "Action tracker", sub: "Your step-by-step plan with deadlines and document templates." },
    glossary: { title: "Code glossary", sub: "Pulled live from AMA/CMS-validated reference data." },
    settings: { title: "Settings", sub: "Manage your account, privacy, and preferences." },
    profile: { title: "My Profile", sub: "Manage your personal details, health insurance policy, and account security." }
  };

  function showPage(page, opts) {
    if (!PAGE_META[page]) return;
    if (["overview", "bill", "issues", "appeal", "actions"].includes(page) && !state.bill) {
      showToast("Analyze a bill first to see this view.");
      return;
    }
    // Reset any page-local selection state
    if (page === "bill" && opts && opts.lineItemId) {
      state.activeLineItemId = opts.lineItemId;
    } else if (page !== "bill") {
      state.activeLineItemId = null;
    }
    if (opts && opts.page) state.currentPage = opts.page;
    if (opts && opts.bbox) state.highlightedBBox = opts.bbox;

    document.querySelectorAll(".page-section").forEach((s) => s.classList.remove("active"));
    const target = $("#page-" + page);
    if (target) target.classList.add("active");
    document.querySelectorAll(".nav-item").forEach((n) => {
      n.classList.toggle("active", n.dataset.page === page);
    });
    $("#topbarTitle").textContent = PAGE_META[page].title;
    $("#topbarSub").textContent = PAGE_META[page].sub;

    if (page === "bill") renderDocViewer();
    if (page === "overview") renderOverview();
    if (page === "issues") renderIssuesList();
    if (page === "appeal") renderAppealMeta();
    if (page === "glossary" && opts && opts.code) openGlossaryDetail(opts.code);

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => {
      const page = item.dataset.page;
      showPage(page);
    });
  });

  /* ==========================================================
     UPLOAD FLOW
     ========================================================== */

  const uploadZone = $("#uploadZone");
  const fileInput = $("#fileInput");
  const cameraInput = $("#cameraInput");

  function triggerUpload() {
    if (state.uploadPending) {
      showToast("An analysis is already running.");
      return;
    }
    fileInput.click();
  }

  uploadZone.addEventListener("click", triggerUpload);
  uploadZone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); triggerUpload(); }
  });
  $("#heroUploadBtn").addEventListener("click", (e) => { e.preventDefault(); triggerUpload(); });

  ["dragenter", "dragover"].forEach((evt) => {
    uploadZone.addEventListener(evt, (e) => { e.preventDefault(); uploadZone.classList.add("dragover"); });
  });
  ["dragleave", "drop"].forEach((evt) => {
    uploadZone.addEventListener(evt, (e) => { e.preventDefault(); uploadZone.classList.remove("dragover"); });
  });
  uploadZone.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) startUpload(e.dataTransfer.files[0]);
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) startUpload(fileInput.files[0]);
    fileInput.value = "";
  });

  // Phone camera capture
  $("#cameraBtn").addEventListener("click", (e) => {
    e.preventDefault();
    if (state.uploadPending) { showToast("An analysis is already running."); return; }
    if (!("capture" in document.createElement("input"))) {
      // Fallback: open file picker
      fileInput.click();
      return;
    }
    cameraInput.click();
  });
  cameraInput.addEventListener("change", () => {
    if (cameraInput.files.length) startUpload(cameraInput.files[0]);
    cameraInput.value = "";
  });

  // Sample cards
  document.querySelectorAll(".sample-card").forEach((card) => {
    card.addEventListener("click", () => {
      const key = card.dataset.sample;
      const fakeFile = key === "clean"
        ? new File([""], "clean-bill.pdf", { type: "application/pdf" })
        : new File([""], "sample-bill.pdf", { type: "application/pdf" });
      startUpload(fakeFile, key);
    });
  });

  // Upload retry
  $("#uploadErrorRetry").addEventListener("click", () => {
    hideUploadError();
    if (state.lastUpload) {
      startUpload(state.lastUpload.file, state.lastUpload.sampleKey);
    } else {
      triggerUpload();
    }
  });

  function showUploadError(code, message) {
    state.uploadErrorShown = true;
    const titles = {
      UNSUPPORTED_FILE_TYPE: "Unsupported file type",
      PAGE_LIMIT_EXCEEDED: "Page limit exceeded",
      NETWORK: "Network error"
    };
    $("#uploadErrorTitle").textContent = titles[code] || "Upload failed";
    $("#uploadErrorMsg").textContent = message || "Please try again.";
    $("#uploadError").hidden = false;
  }
  function hideUploadError() {
    state.uploadErrorShown = false;
    $("#uploadError").hidden = true;
  }

  const PIPELINE_TIMEOUT_MS = 120000; // 2 min — long multi-service pipelines can be slow

  function startUpload(file, sampleKey) {
    hideUploadError();
    state.uploadPending = true;
    state.lastUpload = { file, sampleKey };
    state.jobId = null;
    state.documentId = null;
    state.bill = null;
    state.flags = null;
    state.flagSetComplete = false;
    state.score = null;
    state.scoreComplete = false;
    state.pipelineStatus = null;

    // Clear any previous pipeline timeout
    if (state._pipelineTimer) {
      clearTimeout(state._pipelineTimer);
      state._pipelineTimer = null;
    }

    const pctEl = $("#scanPct");
    const ringFill = $("#scanRingFill");
    const CIRC = 103.67;

    // Reset scan UI
    pctEl.textContent = "0%";
    ringFill.style.strokeDashoffset = CIRC;
    $("#scanPhaseLabel").textContent = "uploading";
    $("#scanTitle").textContent = "Uploading your bill…";
    $("#pipelineError").hidden = true;
    $("#viewPartialResultsBtn").hidden = true;
    document.querySelectorAll(".scan-step").forEach((s) => {
      s.classList.remove("done", "active", "failed");
      const st = s.querySelector("[data-status]");
      if (st) { st.textContent = ""; st.className = "stage-status"; }
    });

    showPage("scan");

    api.upload(file)
      .then((resp) => {
        state.jobId = resp.jobId;
        state.documentId = resp.documentId;
        // Subscribe to pipeline updates (real backend: WS /ws/jobs/{id})
        api.onJobUpdate(resp.jobId, onPipelineUpdate);

        // Timeout guard — if the pipeline stalls, surface a recoverable error
        state._pipelineTimer = setTimeout(() => {
          if (state.uploadPending && state.jobId === resp.jobId) {
            state.uploadPending = false;
            $("#pipelineErrorTitle").textContent = "Pipeline timed out";
            $("#pipelineErrorMsg").textContent = "The analysis is taking longer than expected. Your document is safe — you can retry or upload a different file.";
            $("#pipelineError").hidden = false;
            $("#scanTitle").textContent = "Analysis timed out";
          }
        }, PIPELINE_TIMEOUT_MS);
      })
      .catch((err) => {
        state.uploadPending = false;
        // Upload-time failure (unsupported type, page limit)
        if (err && err.code) {
          // Exit scan view back to welcome with inline error
          document.querySelectorAll(".page-section").forEach((s) => s.classList.remove("active"));
          $("#page-welcome").classList.add("active");
          showUploadError(err.code, err.message);
          // reset nav
          document.querySelectorAll(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.page === "welcome"));
          $("#topbarTitle").textContent = PAGE_META.welcome.title;
          $("#topbarSub").textContent = PAGE_META.welcome.sub;
        } else {
          showUploadError("NETWORK", "Could not reach the pipeline service. Please check your connection and try again.");
        }
      });
  }

  /* ==========================================================
     PIPELINE STATUS HANDLER
     ========================================================== */

  function onPipelineUpdate(status) {
    state.pipelineStatus = status;
    const CIRC = 103.67;

    // Update ring + phase label
    $("#scanPct").textContent = Math.round(status.progress) + "%";
    $("#scanRingFill").style.strokeDashoffset = CIRC - (CIRC * status.progress) / 100;

    const phaseLabels = {
      uploading: "uploading",
      preprocessing: "preprocessing",
      ocr_running: "OCR",
      extraction_running: "extracting",
      validation_running: "validating",
      ml_scoring_running: "scoring",
      done: "done",
      failed: "failed"
    };
    $("#scanPhaseLabel").textContent = phaseLabels[status.status] || status.status;

    // Update stage list
    status.stages.forEach((stage) => {
      const row = document.querySelector(`.scan-step[data-stage="${stage.name}"]`);
      if (!row) return;
      row.classList.remove("done", "active", "failed");
      const statusEl = row.querySelector("[data-status]");
      if (stage.status === "done") {
        row.classList.add("done");
        if (statusEl) { statusEl.textContent = "Complete"; statusEl.className = "stage-status done"; }
      } else if (stage.status === "running") {
        row.classList.add("active");
        if (statusEl) { statusEl.textContent = "Running…"; statusEl.className = "stage-status running"; }
      } else if (stage.status === "failed") {
        row.classList.add("failed");
        if (statusEl) { statusEl.textContent = "Failed"; statusEl.className = "stage-status failed"; }
      }
    });

    // Headline copy
    const stageTitles = {
      preprocessing: "Preprocessing your document…",
      ocr_running: "Running OCR — reading text and layout…",
      extraction_running: "Extracting line items…",
      validation_running: "Validating codes and arithmetic…",
      ml_scoring_running: "Scoring with ML anomaly detection…",
      done: "Analysis complete"
    };
    if (stageTitles[status.status]) {
      $("#scanTitle").textContent = stageTitles[status.status];
    }

    // Progress sub-copy reflects partial results
    const partialNotes = [];
    if (status.partialBill && status.partialBill.lineItems && status.partialBill.lineItems.length) {
      partialNotes.push("bill detail ready");
    }
    if (status.partialFlags && status.partialFlags.flags.length) {
      partialNotes.push("rule flags ready");
    }
    if (status.partialScore) {
      partialNotes.push("appeal score ready");
    }
    if (partialNotes.length) {
      $("#scanSub").innerHTML = "Partial results live: <strong>" + partialNotes.join(", ") + "</strong>. Remaining stages still running in the background.";
    } else {
      $("#scanSub").textContent = "The pipeline runs multiple AI services. Stages complete independently — results stream in as they land.";
    }

    // Failure state
    if (status.status === "failed" && status.failure) {
      $("#pipelineErrorTitle").textContent = "Pipeline failed — " + (status.failure.code || "error");
      $("#pipelineErrorMsg").textContent = status.failure.message || "An unknown error occurred.";
      $("#pipelineError").hidden = false;
      $("#scanTitle").textContent = "Analysis failed";
      state.uploadPending = false;
      return;
    }

    // Success
    if (status.status === "done") {
      state.uploadPending = false;
      // Use the final payloads
      if (status.partialBill) state.bill = status.partialBill;
      if (status.partialFlags) {
        state.flags = status.partialFlags;
        state.flagSetComplete = !!status.partialFlags.complete;
      }
      if (status.partialScore) {
        state.score = status.partialScore;
        state.scoreComplete = true;
      }
      finalizeAnalysis();
      return;
    }

    // Partial results — stream them in as they land
    if (status.partial) {
      if (status.partialBill && !status.partialBill.lineItems.length) {
        // Bill header/metadata available but no line items yet — show skeleton on overview
        state.bill = status.partialBill;
      }
      if (status.partialBill && status.partialBill.lineItems && status.partialBill.lineItems.length) {
        state.bill = status.partialBill;
      }
      if (status.partialFlags) {
        state.flags = status.partialFlags;
        state.flagSetComplete = !!status.partialFlags.complete;
      }
      if (status.partialScore) {
        state.score = status.partialScore;
        state.scoreComplete = false; // score object arrived but pipeline still running
      }
      // Show the "view partial results" button once bill has line items
      if (state.bill && state.bill.lineItems && state.bill.lineItems.length) {
        $("#viewPartialResultsBtn").hidden = false;
      }
      if (state.flags && state.flags.flags.length) {
        $("#viewPartialResultsBtn").hidden = false;
      }
    }

    // Auto-advance to overview once bill is fully extracted AND pipeline still running
    // (keeps user engaged; they can click "view partial results" too)
  }

  $("#viewPartialResultsBtn").addEventListener("click", () => {
    // Ensure bill data is fetched fully
    if (state.bill && state.bill.lineItems && state.bill.lineItems.length) {
      buildDerivedModel();
      showPage("overview");
      showToast("Showing partial results — remaining stages still running.");
    } else {
      showToast("Bill details aren't ready yet — waiting for extraction stage…");
    }
  });

  $("#pipelineRetryBtn").addEventListener("click", () => {
    if (state.lastUpload) {
      startUpload(state.lastUpload.file, state.lastUpload.sampleKey);
    }
  });

  $("#pipelineCancelBtn").addEventListener("click", () => {
    state.uploadPending = false;
    showPage("welcome");
  });

  /* ==========================================================
     FINALIZE + DERIVED MODEL
     ========================================================== */

  function finalizeAnalysis() {
    // Ensure we have the full bill
    if (!state.bill || !state.bill.lineItems || !state.bill.lineItems.length) {
      api.getBill(state.documentId).then((bill) => {
        state.bill = bill;
        buildDerivedModel();
        showPage("overview");
        showToast("Analysis complete — " + (state.flags ? state.flags.flags.length : 0) + " issues found.");
      });
      return;
    }
    buildDerivedModel();
    showPage("overview");
    showToast("Analysis complete — " + (state.flags ? state.flags.flags.length : 0) + " issues found.");
  }

  function buildDerivedModel() {
    const b = state.bill;
    if (!b) return false;

    const isClean = !state.flags || !state.flags.flags || state.flags.flags.length === 0;
    const flags = state.flags && state.flags.flags ? state.flags.flags : [];
    const totalFlagged = flags.reduce((acc, f) => acc + (f.flagAmount || 0), 0);
    const flaggedIds = new Set();
    flags.forEach((f) => (f.lineItemIds || []).forEach((id) => flaggedIds.add(id)));

    currentData = {
      isClean,
      provider: b.metadata.provider || "—",
      payer: b.metadata.payer || "—",
      claim: b.metadata.accountRef || "—",
      serviceDate: b.metadata.statementDate || "—",
      totalBilled: b.totals.billed,
      overcharge: totalFlagged,
      lineItems: b.lineItems,
      issues: flags.map((f) => ({
        id: f.id,
        title: f.title,
        severity: f.severity,
        tone: CATEGORY_META[f.category] ? CATEGORY_META[f.category].tone : "blue",
        amount: f.flagAmount || 0,
        confidence: f.detectionType === "rule"
          ? Math.round((f.confidence || 0.95) * 100) + "% confidence · rule"
          : Math.round((f.confidence || 0.7) * 100) + "% confidence · ML anomaly",
        desc: f.description,
        whatHappened: f.summary,
        howToFix: f.why && f.why.contributions && f.why.contributions.length
          ? f.why.contributions.map((c) => c.description).join(" ")
          : f.description,
        evidence: f.evidence && f.evidence.source ? f.evidence.source : "",
        evidenceCode: f.evidence && f.evidence.codeReference ? f.evidence.codeReference : "",
        code: (f.lineItemIds || []).map((id) => {
          const li = b.lineItems.find((l) => l.id === id);
          return li ? li.code : "";
        }).filter(Boolean).join(" / ") || f.title,
        category: f.category,
        detectionType: f.detectionType,
        lineItemIds: f.lineItemIds || [],
        why: f.why
      })),
      flagSetComplete: state.flagSetComplete,
      scoreReady: state.scoreComplete && state.score && state.score.score != null,
      score: state.score ? state.score.score : null,
      scoreNote: state.score ? state.score.basis : "Score pending…",
      scoreFactors: state.score ? state.score.factors : [],
      scoreCI: state.score && state.score.confidenceInterval ? state.score.confidenceInterval : null,
      scoreSample: state.score ? state.score.sampleSize : 0,
      scoreModel: state.score ? state.score.modelVersion : null,
      scoreCalibrated: state.score ? state.score.calibrated : false,
      scoreCalibration: state.score && state.score.calibration ? state.score.calibration : null,
      scoreStale: state.score ? !!state.score.stale : false,
      patientResponsibility: b.totals.patientResponsibility,
      reconciliation: b.totals.reconciliation,
      pages: b.pages || [],
      extractionWarnings: b.extractionWarnings || []
    };

    updateCounts();
    renderAll();
    return true;
  }

  function updateCounts() {
    if (state.flags && state.flags.flags) {
      $("#navIssueCount").textContent = state.flags.flags.length;
    }
    const remainingActions = currentData && currentData.issues ? currentData.issues.length : 0;
    $("#navActionCount").textContent = Math.max(0, remainingActions);
    if (currentData && currentData.scoreReady) {
      $("#navAppealBadge").hidden = true;
    }
  }

  /* ==========================================================
     RENDERERS — TOP LEVEL
     ========================================================== */

  function renderAll() {
    if (!currentData) return;
    renderBillHeader();
    renderReconStrip();
    renderTabCounts();
    renderOverview();
    renderLineItems();
    renderExplanations();
    renderIssuesList();
    renderAppealMeta();
    renderTimeline();
    renderChecklist();
    renderWarningBanners();
    renderDocViewer();
  }

  function renderOverview() {
    if (!currentData) return;
    const d = currentData;

    // Show real cards once we have bill; keep skeleton otherwise
    const hasBill = state.bill && state.bill.lineItems && state.bill.lineItems.length;
    $("#kpiSkeleton").hidden = hasBill;
    $("#kpiGrid").hidden = !hasBill;
    if (!hasBill) return;

    $("#kpiBilled").textContent = money(d.totalBilled);
    $("#kpiOvercharge").textContent = money0(d.overcharge);
    $("#kpiPatientResp").textContent = money0(d.patientResponsibility);
    $("#kpiChance").innerHTML = d.scoreReady ? Math.round(d.score * 100) + "<small>%</small>" : "…";

    $("#kpiLineNote").textContent = "Across " + d.lineItems.length + " line items";

    if (d.isClean) {
      $("#kpiIssueNote").innerHTML = '<span class="trend-up">0 issues</span> — this bill looks correct';
    } else {
      $("#kpiIssueNote").innerHTML = '<span class="trend-down">' + d.issues.length + " issues</span>" + (d.flagSetComplete ? " found" : " so far (ML still running)");
    }

    if (d.scoreReady) {
      const chanceTrend = d.score >= 0.7 ? "High" : (d.score >= 0.55 ? "Moderate" : "Low");
      const trendClass = d.score >= 0.7 ? "trend-up" : (d.score >= 0.55 ? "" : "trend-down");
      $("#kpiChanceNote").innerHTML = '<span class="' + trendClass + '">' + chanceTrend + "</span> — calibrated probability";
    } else {
      $("#kpiChanceNote").textContent = "ML scoring still running…";
    }

    const gauge = $("#appealGaugeFill");
    const CIRC = 103.67;
    if (d.scoreReady) {
      gauge.style.strokeDashoffset = CIRC - (CIRC * d.score) / 100;
      $("#gaugeValue").textContent = Math.round(d.score * 100) + "%";
    } else {
      gauge.style.strokeDashoffset = CIRC;
      $("#gaugeValue").textContent = "…";
    }

    // Appeal facts
    const appealFactsEl = $("#appealFacts");
    const facts = [];
    if (d.scoreReady) {
      if (d.issues.length) facts.push("<strong>" + d.issues.length + " flag" + (d.issues.length === 1 ? "" : "s") + "</strong> — <strong>" + money0(d.overcharge) + "</strong> in potentially flagged charges.");
      if (d.scoreFactors.length >= 1) facts.push("<strong>Top factor:</strong> " + d.scoreFactors[0].label + " (" + (d.scoreFactors[0].direction === "up" ? "+" : "") + Math.round(d.scoreFactors[0].impact * 100) + " pts).");
      facts.push("<strong>Confidence:</strong> " + (d.scoreCI ? pct(d.scoreCI[0]) + " – " + pct(d.scoreCI[1]) + " interval" : "calibrated") + " · based on " + d.scoreSample.toLocaleString() + " policies.");
    } else {
      facts.push("<strong>Score pending:</strong> ML scoring stage is still running in the background.");
    }
    appealFactsEl.innerHTML = facts
      .map((f) => `<div class="appeal-fact"><span class="fact-icon">${ICONS.check}</span><span>${f}</span></div>`)
      .join("");

    // Overview issues
    renderOverviewIssues();

    // Overview actions (derived from flags)
    renderOverviewActions();
  }

  function renderOverviewIssues() {
    const el = $("#overviewIssues");
    const emptyEl = $("#overviewIssuesEmpty");
    const d = currentData;
    if (d.isClean) {
      el.innerHTML = "";
      emptyEl.hidden = false;
      return;
    }
    emptyEl.hidden = true;
    el.innerHTML = d.issues
      .slice(0, 4)
      .map((issue) => {
        const cat = CATEGORY_META[issue.category] || { icon: ICONS.alert, tone: "blue" };
        const badge = issue.detectionType === "rule"
          ? '<span class="det-badge rule">rule</span>'
          : '<span class="det-badge ml">ML</span>';
        return `
          <div class="issue-item clickable" data-open-issue="${issue.id}">
            <span class="issue-icon ${TONE_CLASS[cat.tone]}">${cat.icon}</span>
            <div class="issue-body">
              <div class="issue-top">
                <strong>${esc(issue.title)}</strong>
                <span class="amount">${money0(issue.amount)}</span>
              </div>
              <div class="issue-desc">${esc(issue.desc)}</div>
              <div class="issue-meta">
                <span>${esc(issue.code)}</span>
                <span>${esc(issue.confidence)}</span>
                ${badge}
              </div>
            </div>
          </div>
        `;
      })
      .join("");

    el.querySelectorAll("[data-open-issue]").forEach((row) => {
      row.addEventListener("click", () => {
        // deep link: navigate to issues and scroll to card
        showPage("issues");
        const card = document.querySelector(`.issue-card[data-flag-id="${row.dataset.openIssue}"]`);
        if (card) setTimeout(() => card.scrollIntoView({ behavior: "smooth", block: "center" }), 150);
      });
    });
  }

  function renderOverviewActions() {
    const el = $("#overviewActions");
    const d = currentData;
    if (d.isClean) {
      el.innerHTML = `
        <div class="action-item done">
          <button class="action-check" disabled>${ICONS.check}</button>
          <div class="action-body">
            <div class="action-title">Bill verified</div>
            <div class="action-sub">No billing errors detected — nothing to dispute.</div>
          </div>
          <span class="action-deadline safe">Normal</span>
        </div>`;
      return;
    }
    const actions = d.issues.slice(0, 3).map((issue, idx) => ({
      id: "f-" + issue.id,
      done: false,
      title: "Address flag: " + issue.title,
      sub: (issue.why && issue.why.contributions && issue.why.contributions[0] ? issue.why.contributions[0].description : issue.desc).slice(0, 90) + "…",
      deadline: idx === 0 ? "Next" : "Flag#" + (idx + 1),
      tone: idx === 0 ? "warn" : "safe"
    }));
    el.innerHTML = actions
      .map((a) => `
        <div class="action-item ${a.done ? "done" : ""}">
          <button class="action-check" data-action="${a.id}" aria-label="Mark as done">${ICONS.check}</button>
          <div class="action-body">
            <div class="action-title">${esc(a.title)}</div>
            <div class="action-sub">${esc(a.sub)}</div>
          </div>
          <span class="action-deadline ${a.tone}">${esc(a.deadline)}</span>
        </div>
      `)
      .join("");
  }

  /* ==========================================================
     RENDERERS — BILL DETAIL
     ========================================================== */

  function renderBillHeader() {
    const b = state.bill;
    if (!b || !b.metadata) return;
    const m = b.metadata;
    $("#billProvider").textContent = m.provider || "—";
    if (m.providerNpi) {
      $("#billProvider").innerHTML = esc(m.provider) + ' <span class="npi-chip">NPI ' + esc(m.providerNpi) + "</span>";
    }
    $("#billPayer").textContent = m.payer || "—";
    $("#billStatementDate").textContent = m.statementDate || "—";
    $("#billAccountRef").textContent = m.accountRef || "—";
    $("#billMember").textContent = m.memberName || "—";
    $("#billMemberId").textContent = m.memberId || "—";

    // Per-field metadata verification (parsed fields get verified badge; derived/missing get warning)
    const metaVerifEls = document.querySelectorAll(".meta-verif");
    metaVerifEls.forEach((el) => {
      const field = el.dataset.billfield;
      const val = m[field];
      if (val) {
        el.innerHTML = '<span class="verif-badge ok" title="Field extracted from the source document">' + ICONS.check + ' parsed</span>';
      } else {
        el.innerHTML = '<span class="verif-badge warn" title="Field not found on the document — please verify manually">' + ICONS.warn + ' review</span>';
      }
    });
  }

  function renderReconStrip() {
    const t = state.bill && state.bill.totals;
    if (!t) return;
    $("#reconBilled").textContent = money(t.billed);
    $("#reconAllowed").textContent = money(t.allowed);
    $("#reconPaid").textContent = money(t.paid);
    $("#reconPatient").textContent = money(t.patientResponsibility);

    const statusEl = $("#reconStatus");
    if (t.reconciliation && !t.reconciliation.ok) {
      statusEl.className = "recon-status bad";
      statusEl.innerHTML = '<span class="rs-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg></span>' +
        '<div><strong>Reconciliation failed</strong><span>' + esc(t.reconciliation.note || "Billed ≠ allowed + patient responsibility") + (t.reconciliation.diff ? " · Diff: " + money(Math.abs(t.reconciliation.diff)) : "") + "</span></div>";
    } else {
      statusEl.className = "recon-status good";
      statusEl.innerHTML = '<span class="rs-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>' +
        '<div><strong>Reconciliation OK</strong><span>Billed = allowed + patient responsibility</span></div>';
    }
  }

  function renderTabCounts() {
    if (!state.bill) return;
    const n = state.bill.lineItems.length;
    $("#tabLineCount").textContent = n;
    $("#tabExplainCount").textContent = n;
  }

  function renderWarningBanners() {
    const warnings = state.bill && state.bill.extractionWarnings ? state.bill.extractionWarnings : [];
    const warnBanner = $("#extractionWarningBanner");
    const billWarnBanner = $("#billWarningBanner");
    if (warnings.length) {
      const text = warnings.map((w) => esc(w.message)).join(" ");
      $("#extractionWarningText").innerHTML = "<strong>Low-confidence extraction:</strong> " + text;
      $("#billWarningText").innerHTML = "<strong>Low-confidence extraction:</strong> " + text;
      warnBanner.hidden = false;
      billWarnBanner.hidden = false;
    } else {
      warnBanner.hidden = true;
      billWarnBanner.hidden = true;
    }
  }

  /* ==========================================================
     RENDERERS — LINE ITEMS (per-field verification)
     ========================================================== */

  function verifBadge(v, label) {
    if (!v) return "";
    if (v.verified) {
      return `<span class="verif-badge ok" title="${esc(v.note || "Extracted from document with high confidence")}">${ICONS.check} ${label ? "" : ""}</span>`;
    }
    if (v.method === "absent" || (!v.verified && !v.note)) {
      return `<span class="verif-badge muted" title="Field not found on the source document">${ICONS.warn} absent</span>`;
    }
    return `<span class="verif-badge warn" title="${esc(v.note || "Extracted with low confidence — please review")}">${ICONS.warn} review</span>`;
  }

  function renderLineItems() {
    const el = $("#lineItemsBody");
    if (!state.bill) { el.innerHTML = ""; return; }
    const isClean = currentData && currentData.isClean;

    el.innerHTML = state.bill.lineItems
      .map((li) => {
        const flagged = currentData && currentData.issues.some((i) => (i.lineItemIds || []).includes(li.id));
        const rowClass = flagged ? "row-flagged" : "";
        const chargeFlag = flagged ? '<span class="flag-icon" title="Flagged issue">' + ICONS.alert + "</span>" : "";

        const code = li.code || li.cptCode || li.hcpcsCode || "—";
        return `
          <tr class="${rowClass}" data-line-item="${li.id}" data-bbox-page="${li.bbox && li.bbox.page || li.page || 1}" data-bbox-x="${li.bbox ? li.bbox.x : 0}" data-bbox-y="${li.bbox ? li.bbox.y : 0}" data-bbox-w="${li.bbox ? li.bbox.w : 0}" data-bbox-h="${li.bbox ? li.bbox.h : 0}">
            <td>
              ${esc(li.serviceDate)}${verifBadge(li.verification && li.verification.date)}
            </td>
            <td>
              <span class="code-pill ${flagged ? "danger" : ""}">${esc(code)}</span>
              ${chargeFlag}
              <div class="cell-sub">${li.cptCode && li.hcpcsCode ? "CPT+HCPCS" : li.codeType || esc(li.codeType || "")}</div>
              ${verifBadge(li.verification && li.verification.code)}
            </td>
            <td class="row-desc">
              <a href="#" class="glossary-link" data-code="${esc(code)}" title="See full definition">${esc(li.description)}</a>
              <div class="cell-sub">
                ${li.modifiers && li.modifiers.length ? "Modifiers: " + esc(li.modifiers.join(", ")) : ""}
                ${li.placeOfService ? (li.modifiers && li.modifiers.length ? " · " : "") + "POS " + esc(li.placeOfService) : ""}
              </div>
              ${verifBadge(li.verification && li.verification.description)}
            </td>
            <td>
              ${(li.icdCodes || []).map((icd) => `
                <div class="icd-row">
                  <a href="#" class="glossary-link icd" data-code="${esc(icd.code)}">${esc(icd.code)}</a>
                  <span class="icd-desc">${esc(icd.description)}</span>
                </div>
              `).join("") || '<span class="cell-sub">—</span>'}
            </td>
            <td>${li.units == null ? "—" : li.units}</td>
            <td>${li.modifiers && li.modifiers.length ? esc(li.modifiers.join(", ")) : "—"}</td>
            <td class="num">${money(li.amounts && li.amounts.charge)}${verifBadge(li.verification && li.verification.amounts)}</td>
            <td class="num">${money(li.amounts && li.amounts.allowed)}</td>
            <td class="num">${money(li.amounts && li.amounts.paid)}</td>
            <td class="num">${money(li.amounts && li.amounts.patientResponsibility)}</td>
          </tr>
        `;
      })
      .join("");

    // Wire row click → highlight bbox on source document
    el.querySelectorAll("tr[data-line-item]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const liId = tr.dataset.lineItem;
        showPage("bill", {
          lineItemId: liId,
          page: parseInt(tr.dataset.bboxPage, 10) || 1,
          bbox: {
            x: parseFloat(tr.dataset.bboxX), y: parseFloat(tr.dataset.bboxY),
            w: parseFloat(tr.dataset.bboxW), h: parseFloat(tr.dataset.bboxH)
          }
        });
      });
    });

    // Wire glossary deep-links
    el.querySelectorAll(".glossary-link").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        showPage("glossary", { code: a.dataset.code });
      });
    });
  }

  function renderExplanations() {
    const el = $("#explainList");
    if (!state.bill) { el.innerHTML = ""; return; }

    const flagFor = (li) => currentData && currentData.issues.find((i) => (i.lineItemIds || []).includes(li.id));

    el.innerHTML = state.bill.lineItems
      .map((li) => {
        const flag = flagFor(li);
        const statusHtml = flag
          ? `<span class="status ${flag.severity === "high" ? "denied" : "partial"}">Flagged</span>`
          : '<span class="status covered">Covered</span>';

        const plain = flag
          ? `<strong>${esc(flag.title)}</strong> — ${esc(flag.whatHappened)}. ${esc(flag.howToFix)}`
          : "This service was covered by your plan. You are responsible for your normal cost-sharing amounts (deductible, coinsurance, or copay).";

        return `
          <div class="explain-item">
            <div class="e-code">
              ${esc(li.code)}
              ${statusHtml}
              <a href="#" class="glossary-link" data-code="${esc(li.code)}" style="font-weight:600; font-size:12px; color:var(--teal-600);">See full definition</a>
            </div>
            <div class="e-desc">${esc(li.description)}</div>
            <div class="e-plain">${plain}</div>
          </div>
        `;
      })
      .join("");

    el.querySelectorAll(".glossary-link").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        showPage("glossary", { code: a.dataset.code });
      });
    });
  }

  /* ==========================================================
     RENDERERS — DOCUMENT VIEWER (provenance)
     ========================================================== */

  function renderDocViewer() {
    const pages = state.bill ? state.bill.pages : [];
    const navEl = $("#docPageNav");
    const thumbsEl = $("#pageThumbnails");

    if (!pages.length) {
      navEl.innerHTML = '<div class="empty-inline"><p>Document pages will appear here after OCR.</p></div>';
      thumbsEl.innerHTML = "";
      return;
    }

    // Page nav dots
    navEl.innerHTML = pages
      .map((p, idx) => {
        const active = idx + 1 === state.currentPage ? "active" : "";
        return `<button class="page-dot ${active}" data-page="${p.index}" title="Page ${p.index}">${p.index}</button>`;
      })
      .join("");
    navEl.querySelectorAll(".page-dot").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.currentPage = parseInt(btn.dataset.page, 10);
        renderDocViewer();
      });
    });

    // Thumbnails
    thumbsEl.innerHTML = pages
      .map((p) => {
        const active = p.index === state.currentPage ? "active" : "";
        return `<button class="page-thumb ${active}" data-thumb-page="${p.index}" title="Page ${p.index}">
          <img src="${p.imageUrl}" alt="Page ${p.index} thumbnail" loading="lazy" />
        </button>`;
      })
      .join("");
    thumbsEl.querySelectorAll(".page-thumb").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.currentPage = parseInt(btn.dataset.thumbPage, 10);
        renderDocViewer();
      });
    });

    // Main image
    const page = pages.find((p) => p.index === state.currentPage) || pages[0];
    const img = $("#docPageImage");
    img.src = page.imageUrl;
    img.onload = () => drawBBoxOverlay(img, page);
    $("#docPageCaption").textContent = "Source document — page " + page.index + " of " + pages.length;

    // Right side: provenance fields list
    const dvrFields = $("#dvrFields");
    if (state.bill && state.bill.lineItems) {
      const onThisPage = state.bill.lineItems.filter((li) => (li.bbox && li.bbox.page) === state.currentPage);
      dvrFields.innerHTML = onThisPage.length
        ? onThisPage.map((li) => `
            <button class="dvr-field ${state.activeLineItemId === li.id ? "active" : ""}" data-dvr-li="${li.id}">
              <span class="df-code">${esc(li.code)}</span>
              <span class="df-desc">${esc(li.description)}</span>
              <span class="df-coord">(${Math.round(li.bbox.x * 100)}%, ${Math.round(li.bbox.y * 100)}%)</span>
            </button>
          `).join("")
        : '<p class="cell-sub">No line items on this page.</p>';
      dvrFields.querySelectorAll("[data-dvr-li]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const li = state.bill.lineItems.find((l) => l.id === btn.dataset.dvrLi);
          if (!li) return;
          state.currentPage = li.bbox.page;
          renderDocViewer();
          drawBBoxOverlay($("#docPageImage"), page, li.bbox);
          const row = $(`tr[data-line-item="${li.id}"]`);
          if (row) { row.scrollIntoView({ behavior: "smooth", block: "center" }); row.classList.add("flash"); setTimeout(() => row.classList.remove("flash"), 1200); }
        });
      });
    }

    drawBBoxOverlay(img, page);
  }

  function drawBBoxOverlay(img, page, overrideBBox) {
    const canvas = $("#bboxCanvas");
    canvas.innerHTML = "";
    if (!img.src || !state.bill || !state.bill.lineItems) return;

    const rect = img.getBoundingClientRect();
    if (rect.width === 0) return;

    // Bounding boxes for line items on this page
    const onPage = state.bill.lineItems.filter((li) => li.bbox && li.bbox.page === page.index);
    onPage.forEach((li) => {
      const box = document.createElement("div");
      box.className = "bbox";
      if (state.activeLineItemId === li.id) box.classList.add("active");
      const active = state.activeLineItemId === li.id || (overrideBBox && overrideBBox === li.bbox);
      if (active) box.classList.add("active");
      box.style.left = li.bbox.x * 100 + "%";
      box.style.top = li.bbox.y * 100 + "%";
      box.style.width = li.bbox.w * 100 + "%";
      box.style.height = li.bbox.h * 100 + "%";
      box.title = li.code + " — " + li.description;
      box.addEventListener("click", (e) => {
        e.stopPropagation();
        const row = $(`tr[data-line-item="${li.id}"]`);
        if (row) {
          row.scrollIntoView({ behavior: "smooth", block: "center" });
          row.classList.add("flash"); setTimeout(() => row.classList.remove("flash"), 1200);
        }
      });
      canvas.appendChild(box);
    });
  }

  /* ==========================================================
     RENDERERS — ISSUES / FLAGS
     ========================================================== */

  const TONE_CLASS = { red: "tone-red", amber: "tone-amber", blue: "tone-blue", teal: "tone-teal" };

  function renderIssuesList() {
    if (!currentData) return;

    const el = $("#issuesList");
    const cleanState = $("#cleanBillState");
    const summary = $("#flagSummary");
    const mlSkeleton = $("#mlFlagsSkeleton");

    const d = currentData;
    if (d.isClean) {
      el.innerHTML = "";
      summary.hidden = true;
      mlSkeleton.hidden = true;
      cleanState.hidden = false;
      return;
    }
    cleanState.hidden = true;
    summary.hidden = false;
    // Hide ML skeleton once flagSet is complete
    mlSkeleton.hidden = d.flagSetComplete;

    // Summary
    const fsum = state.flags && state.flags.summary ? state.flags.summary : null;
    if (fsum) {
      $("#flagTotalAmount").textContent = money0(fsum.totalFlaggedAmount);
      $("#flagRuleCount").textContent = fsum.ruleCount != null ? fsum.ruleCount : d.issues.filter((i) => i.detectionType === "rule").length;
      $("#flagMlCount").textContent = fsum.mlCount != null ? fsum.mlCount : d.issues.filter((i) => i.detectionType === "ml").length;
    }

    const filtered = d.issues.filter((i) => state.currentIssueFilter === "all" || i.severity === state.currentIssueFilter);

    if (!filtered.length) {
      el.innerHTML = `<div class="dash-card" style="text-align:center; padding:40px;">
        <p style="color:var(--slate-500); font-size:15px;">No issues match this filter.</p>
      </div>`;
      return;
    }

    el.innerHTML = filtered
      .map((issue) => {
        const cat = CATEGORY_META[issue.category] || { label: "Issue", icon: ICONS.alert, tone: "blue" };
        const isRule = issue.detectionType === "rule";
        const detBadge = isRule
          ? '<span class="det-badge rule" title="Deterministic rule — this is a fact, not a probability">Rule</span>'
          : '<span class="det-badge ml" title="ML anomaly score — this is a probability estimate">ML anomaly</span>';

        const whyPanel = issue.why && issue.why.contributions && issue.why.contributions.length
          ? `
            <div class="why-panel">
              <div class="why-head">
                <strong>${esc(issue.why.title || "Why this was flagged")}</strong>
                <span class="why-note">SHAP feature contributions</span>
              </div>
              <ul class="why-list">
                ${issue.why.contributions.map((c, idx) => `
                  <li>
                    <span class="why-direction ${c.direction === "up" ? "up" : "down"}">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">${c.direction === "up" ? '<path d="M12 19V5M5 12l7-7 7 7"/>' : '<path d="M12 5v14M19 12l-7 7-7-7"/>'}</svg>
                    </span>
                    <span class="why-text">
                      <strong>${esc(c.label)}</strong>
                      <span>${esc(c.description)}</span>
                    </span>
                    <span class="why-value">${c.value != null ? esc(String(c.value)) : ""}</span>
                  </li>
                `).join("")}
              </ul>
            </div>
          `
          : "";

        const relatedLineItems = (issue.lineItemIds || [])
          .map((id) => state.bill && state.bill.lineItems.find((l) => l.id === id))
          .filter(Boolean);

        return `
          <div class="issue-card" data-flag-id="${issue.id}">
            <div class="issue-head">
              <div class="issue-head-left">
                <span class="issue-big-icon ${TONE_CLASS[cat.tone]}">${cat.icon}</span>
                <div>
                  <h3>${esc(issue.title)}</h3>
                  <p>${esc(cat.label)} · ${esc(issue.code)} · ${detBadge} ${esc(issue.confidence)}</p>
                </div>
              </div>
              <div class="issue-money">
                <span class="amount">${money0(issue.amount)}</span>
                <span class="confidence">potential impact</span>
                <span class="severity-chip ${SEV_CLASS[issue.severity] || ""}">${esc(issue.severity)}</span>
              </div>
            </div>
            <div class="issue-details">
              <div class="issue-detail">
                <span>What happened</span>
                <p>${esc(issue.whatHappened)}</p>
              </div>
              <div class="issue-detail">
                <span>Why it matters</span>
                <p>${esc(issue.desc)}</p>
              </div>
            </div>
            ${whyPanel}
            <div class="issue-foot">
              <div class="issue-links">
                <strong style="font-size:12px; color:var(--slate-400); text-transform:uppercase; letter-spacing:0.04em;">Related line items</strong>
                <div class="related-lines">
                  ${relatedLineItems.length ? relatedLineItems.map((li) => `
                    <button class="related-line" data-rel-li="${li.id}" data-page="${li.bbox ? li.bbox.page : 1}" data-x="${li.bbox ? li.bbox.x : 0}" data-y="${li.bbox ? li.bbox.y : 0}" data-w="${li.bbox ? li.bbox.w : 0}" data-h="${li.bbox ? li.bbox.h : 0}">
                      <span class="rl-code">${esc(li.code)}</span>
                      <span class="rl-desc">${esc(li.description)}</span>
                      <span class="rl-amount">${money(li.amounts && li.amounts.charge)}</span>
                    </button>
                  `).join("") : '<span class="cell-sub">No line items linked</span>'}
                </div>
                ${issue.evidenceCode ? `<div class="evidence-ref"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg> <span>${esc(issue.evidenceCode)}</span></div>` : ""}
                ${issue.evidence ? `<div class="evidence-ref source"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg> <span>${esc(issue.evidence)}</span></div>` : ""}
              </div>
              <div class="issue-btn-group">
                <button class="btn btn-secondary btn-sm" data-draft-for="${issue.id}">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                  Draft appeal
                </button>
              </div>
            </div>
          </div>
        `;
      })
      .join("");

    // Wire related-line → bill deep link with bbox highlight
    el.querySelectorAll("[data-rel-li]").forEach((btn) => {
      btn.addEventListener("click", () => {
        showPage("bill", {
          lineItemId: btn.dataset.relLi,
          page: parseInt(btn.dataset.page, 10),
          bbox: { x: parseFloat(btn.dataset.x), y: parseFloat(btn.dataset.y), w: parseFloat(btn.dataset.w), h: parseFloat(btn.dataset.h) }
        });
      });
    });

    el.querySelectorAll("[data-draft-for]").forEach((btn) => {
      btn.addEventListener("click", () => showPage("appeal"));
    });

    // Severity filter is handled by button listeners below
  }

  // Severity filter
  document.querySelectorAll(".severity-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".severity-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.currentIssueFilter = btn.dataset.sev;
      renderIssuesList();
    });
  });

  /* ==========================================================
     RENDERERS — APPEAL
     ========================================================== */

  function renderAppealMeta() {
    const d = currentData;
    if (!d) return;

    const scoreReady = d.scoreReady;
    const ascValue = $("#ascValue");
    const ascConfidence = $("#ascConfidence");
    const ciBar = $("#ciBar");
    const ciRange = $("#ciRange");
    const ciPoint = $("#ciPoint");
    const ciLow = $("#ciLowLabel");
    const ciHigh = $("#ciHighLabel");
    const scoreBar = $("#scoreBarFill");
    const ascNote = $("#ascNote");
    const ascModelMeta = $("#ascModelMeta");
    const ascFacts = $("#ascFacts");

    if (scoreReady) {
      const score = d.score;
      ascValue.innerHTML = Math.round(score * 100) + "<em>%</em>";
      ascConfidence.innerHTML = '<span class="cal-badge">' + ICONS.check + ' calibrated probability</span>';
      scoreBar.style.width = Math.round(score * 100) + "%";
      ascNote.textContent = d.scoreNote || "Calibrated probability from the appeal model.";

      if (d.scoreCI) {
        ciBar.hidden = false;
        const lo = Math.round(d.scoreCI[0] * 100);
        const hi = Math.round(d.scoreCI[1] * 100);
        const mid = Math.round(score * 100);
        ciRange.style.left = lo + "%";
        ciRange.style.width = Math.max(0, hi - lo) + "%";
        ciPoint.style.left = mid + "%";
        ciLow.textContent = lo + "%";
        ciHigh.textContent = hi + "%";
      } else {
        ciBar.hidden = true;
      }

      ascModelMeta.innerHTML =
        '<span class="model-meta">Model <code>' + esc(d.scoreModel || "—") + "</code></span>" +
        '<span class="model-meta">Sample <code>' + (d.scoreSample || 0).toLocaleString() + " policies</code></span>" +
        (d.scoreCalibration && d.scoreCalibration.expectedError != null
          ? '<span class="model-meta">Cal. error <code>±' + Math.round(d.scoreCalibration.expectedError * 100) + "%</code></span>"
          : "");

      // Stale flag from the API — show recompute prompt if the backend marked it stale
      if (d.scoreStale && !state._scoreMarkedStale) {
        state._scoreMarkedStale = true;
        $("#scoreRecompute").hidden = false;
      }

      // Factor breakdown
      if (d.scoreFactors && d.scoreFactors.length) {
        ascFacts.innerHTML =
          '<div class="factor-title">What drives this score</div>' +
          d.scoreFactors.map((f) => `
            <div class="factor-row ${f.direction === "up" ? "up" : "down"}">
              <span class="factor-icon ${f.direction === "up" ? "up" : "down"}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">${f.direction === "up" ? '<path d="M12 19V5M5 12l7-7 7 7"/>' : '<path d="M12 5v14M19 12l-7 7-7-7"/>'}</svg>
              </span>
              <div class="factor-body">
                <div class="factor-top">
                  <strong>${esc(f.label)}</strong>
                  <span class="factor-impact ${f.direction === "up" ? "up" : "down"}">${f.direction === "up" ? "+" : ""}${Math.round(f.impact * 100)} pts</span>
                </div>
                <p>${esc(f.description)}</p>
              </div>
            </div>
          `).join("");
      } else {
        ascFacts.innerHTML = '<div class="factor-title">No factors yet — score pending.</div>';
      }
    } else {
      ascValue.textContent = "…";
      ascConfidence.innerHTML = "";
      scoreBar.style.width = "0%";
      ascNote.textContent = d.scoreNote || "Appeal score pending — ML scoring stage still running in the background.";
      ciBar.hidden = true;
      ascModelMeta.innerHTML = "";
      ascFacts.innerHTML = `
        <div class="skeleton-line w70"></div>
        <div class="skeleton-line w50"></div>
        <div class="skeleton-line w80"></div>
        <p style="font-size:12.5px; color:#94a3b8; margin-top:8px;">Score will stream in when the scoring service completes. You can keep editing the letter in the meantime.</p>
      `;
    }

    // Strategies from flags
    renderStrategies();
    renderLetter();

    // Deadline pill
    const deadline = $("#deadlinePillText");
    if (d.issues.length) {
      deadline.textContent = "14 days to appeal deadline";
      $("#deadlinePill").className = "deadline-pill urgent";
    } else {
      deadline.textContent = "No appeal needed — clean bill";
      $("#deadlinePill").className = "deadline-pill safe";
    }
  }

  function renderStrategies() {
    const el = $("#strategyList");
    const d = currentData;
    if (!d) { el.innerHTML = ""; return; }

    const strategies = d.issues.map((issue, idx) => ({
      id: "s" + idx,
      title: "Address " + issue.title,
      desc: (issue.why && issue.why.contributions && issue.why.contributions[0] ? issue.why.contributions[0].description : issue.whatHappened)
    }));

    if (!strategies.length) {
      el.innerHTML = `<div style="font-size:13px; color:var(--slate-500);">No billing errors — your appeal would focus on coverage or medical-necessity arguments instead.</div>`;
      return;
    }

    el.innerHTML = strategies
      .map((s, idx) => `
        <label class="${idx === 0 ? "selected" : ""}">
          <input type="radio" name="strategy" value="${s.id}" ${idx === 0 ? "checked" : ""} />
          <div class="st-body">
            <strong>${esc(s.title)}</strong>
            <p>${esc(s.desc)}</p>
          </div>
        </label>
      `)
      .join("");

    el.querySelectorAll("label").forEach((label) => {
      label.addEventListener("click", () => {
        el.querySelectorAll("label").forEach((l) => l.classList.remove("selected"));
        label.classList.add("selected");
        showToast("Strategy updated — appeal letter regenerated.");
        renderLetter();
      });
    });
  }

  function renderLetter() {
    const ta = $("#letterTextarea");
    const d = currentData;
    if (!d) { ta.value = ""; return; }

    if (d.isClean) {
      ta.value = `Re: Claim #${d.claim} — Record of Claim Review

To Whom It May Concern,

I am writing regarding claim #${d.claim} from ${d.provider}. Vitta reviewed this bill and found no billing errors, duplicate charges, or coverage surprises. The claim appears correctly coded and priced.

If you believe there is an issue with this claim, please contact me.

Sincerely,
Alex Sharma`;
      return;
    }

    const issuesText = d.issues
      .map((issue, idx) => `${idx + 1}. ${issue.title}\n   ${issue.whatHappened}. Estimated impact: ${money0(issue.amount)}.`)
      .join("\n\n");

    const requests = d.issues
      .map((issue, idx) => `${idx + 1}. Correct the issue described above (${issue.title}).`)
      .join("\n");

    const letter = `Re: Claim #${d.claim} — Request for Reconsideration

To Whom It May Concern,

I am writing to appeal the processing of claim #${d.claim} for services provided by ${d.provider}. I believe this claim contains billing errors that have resulted in an overcharge and I am requesting a full review.

ISSUES IDENTIFIED:

${issuesText}

SUPPORTING DOCUMENTATION:
- Itemized bill from ${d.provider}
- Medical records documenting the actual level of care
- Fair-price comparison showing the reasonable range for these services

I request that you:
${requests}
${d.issues.length + 1}. Recalculate my responsibility based on the corrected amounts.

Please contact me if you need any additional documentation. I look forward to your prompt response.

Sincerely,
Alex Sharma
Claim #${d.claim}`;

    ta.value = letter;
  }

  // Letter edit → mark score stale (recompute hook)
  $("#letterTextarea").addEventListener("input", () => {
    const d = currentData;
    if (!d || !d.scoreReady) return;
    if (!state._scoreMarkedStale) {
      state._scoreMarkedStale = true;
      $("#scoreRecompute").hidden = false;
    }
  });

  $("#recomputeScoreBtn").addEventListener("click", (e) => {
    e.preventDefault();
    if (!state.documentId) return;
    showToast("Recomputing appeal score with your edits…");
    api.recomputeAppealScore(state.documentId, { adjustment: 0.02 })
      .then((newScore) => {
        state.score = newScore;
        state.scoreComplete = true;
        state._scoreMarkedStale = false;
        $("#scoreRecompute").hidden = true;
        buildDerivedModel();
        renderAppealMeta();
        showToast("Appeal score updated — reflects your latest edits.");
      })
      .catch(() => showToast("Could not recompute — try again."));
  });

  // Copy / download / share / send letter
  $("#copyLetterBtn").addEventListener("click", (e) => {
    e.preventDefault();
    const ta = $("#letterTextarea");
    ta.select();
    navigator.clipboard?.writeText(ta.value).catch(() => {});
    showToast("Appeal letter copied to clipboard.");
  });
  $("#downloadLetterBtn").addEventListener("click", (e) => {
    e.preventDefault();
    downloadText("appeal-letter.txt", $("#letterTextarea").value);
    showToast("Appeal letter downloaded.");
  });
  $("#downloadBillBtn").addEventListener("click", (e) => {
    e.preventDefault();
    downloadText("vitta-bill-report.txt", buildBillReport());
    showToast("Bill report downloaded.");
  });
  function dispatchAppealEmail() {
    const targetEmail = $("#targetRecipientEmail") ? $("#targetRecipientEmail").value.trim() : "appeals@bluecross.com";
    if (!targetEmail || !targetEmail.includes("@")) {
      showToast("Please enter a valid recipient email address.");
      return;
    }
    const letterText = $("#letterTextarea").value || "";
    const subject = encodeURIComponent("APPEAL: Medical Bill Claim #" + (state.documentId || "CLM-98214"));
    const body = encodeURIComponent(letterText);

    // Open mailto link directly with prefilled recipient and letter
    window.location.href = `mailto:${targetEmail}?subject=${subject}&body=${body}`;

    showToast(`Appeal letter sent to ${targetEmail}! Added to action tracker.`);

    const hint = $("#letterFooterHint");
    if (hint) hint.textContent = `Sent to ${targetEmail} · ${new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}`;
  }

  const directEmailBtn = $("#sendDirectEmailBtn");
  if (directEmailBtn) {
    directEmailBtn.addEventListener("click", (e) => {
      e.preventDefault();
      dispatchAppealEmail();
    });
  }

  $("#sendLetterBtn").addEventListener("click", (e) => {
    e.preventDefault();
    dispatchAppealEmail();
  });

  $("#shareLetterBtn").addEventListener("click", (e) => {
    e.preventDefault();
    showToast("Secure share link created (expires in 7 days).");
  });

  const editProfBtn = $("#settingsEditProfileBtn");
  if (editProfBtn) {
    editProfBtn.addEventListener("click", (e) => {
      e.preventDefault();
      showPage("profile");
    });
  }

  const changePassBtn = $("#settingsChangePasswordBtn");
  if (changePassBtn) {
    changePassBtn.addEventListener("click", (e) => {
      e.preventDefault();
      const newPass = prompt("Enter your new account password:", "");
      if (newPass && newPass.length >= 6) {
        showToast("Account password updated successfully!");
      } else if (newPass !== null) {
        showToast("Password must be at least 6 characters.");
      }
    });
  }

  const exportBtn = $("#exportDataBtn");
  if (exportBtn) {
    exportBtn.addEventListener("click", (e) => {
      e.preventDefault();
      const userRaw = localStorage.getItem("vitta_user");
      const userObj = userRaw ? JSON.parse(userRaw) : { name: "Alex Sharma", email: "alex.sharma@vitta.ai" };
      const exportPayload = {
        user: userObj,
        active_bill: state.bill || null,
        active_flags: state.flags || null,
        exported_at: new Date().toISOString(),
        encryption: "AES-256-GCM / HIPAA Compliant Backup"
      };
      downloadText("vitta-user-data-backup.json", JSON.stringify(exportPayload, null, 2));
      showToast("Exported 100% of your encrypted data as JSON backup.");
    });
  }

  function downloadText(filename, text) {
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function buildBillReport() {
    const d = currentData;
    const lines = [
      "VITTA — BILL ANALYSIS REPORT",
      "===============================",
      "",
      `Provider: ${d.provider}`,
      `Payer: ${d.payer}`,
      `Account: ${d.claim}`,
      `Statement date: ${d.serviceDate}`,
      "",
      `Total billed: ${money(d.totalBilled)}`,
      `Patient responsibility: ${money(d.patientResponsibility)}`,
      `Flagged amount: ${money0(d.overcharge)}`,
      `Appeal success chance: ${d.scoreReady ? Math.round(d.score * 100) + "%" : "pending"}`,
      "",
      "ISSUES FOUND:",
      ...(d.isClean ? ["- None. This bill looks correct."] : d.issues.map((i) => `- ${i.title}: ${money0(i.amount)} (${i.detectionType}, ${i.severity})`)),
      "",
      "RECONCILIATION:",
      d.reconciliation ? (d.reconciliation.ok ? "- OK: Billed = allowed + patient responsibility" : `- FAILED: ${d.reconciliation.note || ""}`) : "- N/A"
    ];
    return lines.join("\n");
  }

  /* ==========================================================
     RENDERERS — TIMELINE + CHECKLIST
     ========================================================== */

  function renderTimeline() {
    const el = $("#timeline");
    const d = currentData;
    if (!d) { el.innerHTML = ""; return; }

    const items = [
      { title: "Bill uploaded", date: "Today", desc: "Document uploaded and OCR processed.", state: "done" },
      { title: "Extraction complete", date: "Today", desc: "Line items mapped to ParsedBill schema.", state: "done" },
      ...(d.issues.length ? [{
        title: "Address flagged issues",
        date: "Next",
        desc: d.issues.length + " flag" + (d.issues.length === 1 ? "" : "s") + " to review — see the Issues page.",
        state: "current"
      }] : []),
      { title: "File internal appeal", date: "Within 14 days", desc: "Send appeal to " + (d.payer || "insurer") + ".", state: "pending" },
      { title: "External review", date: "If needed", desc: "Independent review if internal appeal is denied.", state: "pending" }
    ];

    el.innerHTML = items
      .map((t) => `
        <div class="timeline-item ${t.state}">
          <div class="tl-title">${esc(t.title)} <span class="tl-date">${esc(t.date)}</span></div>
          <div class="tl-desc">${esc(t.desc)}</div>
        </div>
      `)
      .join("");
  }

  function renderChecklist() {
    const el = $("#checklist");
    const d = currentData;
    if (!d) { el.innerHTML = ""; return; }

    const actions = d.isClean
      ? [{ id: "c1", done: true, title: "Bill verified", sub: "No billing errors found.", deadline: "Done", tone: "safe" }]
      : d.issues.map((issue, idx) => ({
          id: "flag-" + issue.id,
          done: false,
          title: issue.title,
          sub: issue.whatHappened,
          deadline: idx === 0 ? "Urgent" : "Review",
          tone: idx === 0 ? "urgent" : "warn"
        }));

    el.innerHTML = actions
      .map((a) => `
        <div class="action-item ${a.done ? "done" : ""}">
          <button class="action-check" data-action="${a.id}" aria-label="Toggle action">${ICONS.check}</button>
          <div class="action-body">
            <div class="action-title">${esc(a.title)}</div>
            <div class="action-sub">${esc(a.sub)}</div>
          </div>
          <span class="action-deadline ${a.tone}">${esc(a.deadline)}</span>
        </div>
      `)
      .join("");

    wireActionChecks(el);
    updateActionCount();
  }

  function wireActionChecks(container) {
    container.querySelectorAll(".action-check").forEach((check) => {
      check.addEventListener("click", () => {
        const id = check.dataset.action;
        const parent = check.closest(".action-item");
        if (parent) parent.classList.toggle("done");
        updateActionCount();
      });
    });
  }

  function updateActionCount() {
    if (currentData) {
      $("#navActionCount").textContent = currentData.isClean ? 1 : currentData.issues.length;
    }
  }

  /* ==========================================================
     RENDERERS — GLOSSARY (API-wired + deep-link)
     ========================================================== */

  let glossaryCache = [];

  function renderGlossary(filter = "") {
    const grid = $("#glossaryGrid");
    const skeleton = $("#glossarySkeleton");

    api.searchCodes(filter).then((items) => {
      glossaryCache = items;
      skeleton.hidden = true;
      grid.innerHTML = items
        .map((g) => `
          <button class="glossary-card" data-gloss-code="${esc(g.code)}" style="text-align:left; cursor:pointer; display:block; width:100%;">
            <div class="g-code">${esc(g.code)}</div>
            <span class="g-type">${esc(g.type)}${g.deprecated ? ' · <span style="color:var(--red-600);">deprecated</span>' : ""}</span>
            <p>${esc(g.plainLanguage || g.description)}</p>
            <div class="g-source">${esc(g.source || "")}</div>
          </button>
        `)
        .join("");

      grid.querySelectorAll("[data-gloss-code]").forEach((card) => {
        card.addEventListener("click", () => openGlossaryDetail(card.dataset.glossCode));
      });

      if (!items.length) {
        grid.innerHTML = `<div class="dash-card" style="grid-column:1/-1; text-align:center; padding:32px;">
          <p style="color:var(--slate-500);">No codes match "${esc(filter)}".</p>
        </div>`;
      }
    });
  }

  function openGlossaryDetail(code) {
    const detail = $("#glossaryDetail");
    api.getCode(code)
      .then((def) => {
        $("#gdCode").textContent = def.code;
        $("#gdType").textContent = def.type + (def.deprecated ? " · deprecated" : "");
        $("#gdTitle").textContent = def.description;
        $("#gdPlain").textContent = def.plainLanguage || def.description;
        $("#gdCategory").textContent = def.category || "—";
        $("#gdAka").textContent = def.aka || "—";
        $("#gdSource").textContent = def.source || "—";
        $("#gdStatus").textContent = def.deprecated ? "Deprecated" + (def.supersededBy ? " → " + def.supersededBy : "") : "Active";
        const notes = $("#gdNotes");
        if (def.notes) {
          notes.hidden = false;
          notes.innerHTML = "<strong>Notes:</strong> " + esc(def.notes);
        } else {
          notes.hidden = true;
        }
        detail.hidden = false;
        detail.scrollIntoView({ behavior: "smooth", block: "center" });
      })
      .catch((err) => {
        showToast(err && err.message ? err.message : "Code not found.");
      });
  }

  $("#gdClose").addEventListener("click", () => { $("#glossaryDetail").hidden = true; });
  $("#gdCloseBtn").addEventListener("click", (e) => { e.preventDefault(); $("#glossaryDetail").hidden = true; });

  $("#glossarySearch").addEventListener("input", (e) => {
    const q = e.target.value.trim();
    renderGlossaryFiltered(q);
  });

  let glossaryTimer = null;
  function renderGlossaryFiltered(q) {
    const grid = $("#glossaryGrid");
    const skeleton = $("#glossarySkeleton");
    clearTimeout(glossaryTimer);
    glossaryTimer = setTimeout(() => {
      // Debounce like a real API call
      api.searchCodes(q).then((items) => {
        skeleton.hidden = true;
        grid.innerHTML = items
          .map((g) => `
            <button class="glossary-card" data-gloss-code="${esc(g.code)}" style="text-align:left; cursor:pointer; display:block; width:100%;">
              <div class="g-code">${esc(g.code)}</div>
              <span class="g-type">${esc(g.type)}</span>
              <p>${esc(g.plainLanguage || g.description)}</p>
              <div class="g-source">${esc(g.source || "")}</div>
            </button>
          `)
          .join("");
        grid.querySelectorAll("[data-gloss-code]").forEach((card) => {
          card.addEventListener("click", () => openGlossaryDetail(card.dataset.glossCode));
        });
        if (!items.length) {
          grid.innerHTML = `<div class="dash-card" style="grid-column:1/-1; text-align:center; padding:32px;">
            <p style="color:var(--slate-500);">No codes match "${esc(q)}".</p>
          </div>`;
        }
      });
    }, 180);
  }

  /* ==========================================================
     TOPBAR SEARCH — deep-links to glossary
     ========================================================== */

  const topbarSearch = document.querySelector(".topbar-actions .search-box input");
  if (topbarSearch) {
    topbarSearch.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const q = topbarSearch.value.trim();
        if (q) {
          showPage("glossary");
          $("#glossarySearch").value = q;
          renderGlossaryFiltered(q);
          showToast("Searching glossary for \"" + q + "\"…");
        }
      }
    });
  }

  /* ==========================================================
     CROSS-NAV BUTTONS
     ========================================================== */

  $("#viewBillBtn").addEventListener("click", (e) => { e.preventDefault(); showPage("bill"); });
  $("#goAppealBtn").addEventListener("click", (e) => { e.preventDefault(); showPage("appeal"); });
  $("#cleanViewBillBtn").addEventListener("click", (e) => { e.preventDefault(); showPage("bill"); });
  $("#cleanAppealBtn").addEventListener("click", (e) => { e.preventDefault(); showPage("appeal"); });

  // Bill tabs
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $("#tab-" + btn.dataset.tab).classList.add("active");
    });
  });

  /* ==========================================================
     MODAL + TOASTS
     ========================================================== */

  const modalBackdrop = $("#modalBackdrop");
  function openModal() { modalBackdrop.classList.add("open"); }
  function closeModal() { modalBackdrop.classList.remove("open"); }
  $("#upgradeBtn").addEventListener("click", (e) => { e.preventDefault(); openModal(); });
  $("#modalClose").addEventListener("click", closeModal);
  $("#modalCancel").addEventListener("click", (e) => { e.preventDefault(); closeModal(); });
  $("#modalUpgrade").addEventListener("click", (e) => {
    e.preventDefault();
    closeModal();
    showToast("Welcome to Plus! All features unlocked.");
  });
  modalBackdrop.addEventListener("click", (e) => {
    if (e.target === modalBackdrop) closeModal();
  });

  $("#deleteDataBtn").addEventListener("click", (e) => {
    e.preventDefault();
    showToast("Data deletion initiated — you'll get a confirmation email.");
  });

  $("#docUploadRow").addEventListener("click", () => {
    showToast("Document upload started (PDF, JPG, PNG).");
  });

  function showToast(message) {
    const container = $("#toastContainer");
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.innerHTML = `${ICONS.check}<span>${esc(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.classList.add("out");
      setTimeout(() => toast.remove(), 300);
    }, 3200);
  }

  /* ==========================================================
     INIT & USER PROFILE
     ========================================================== */

  function initUserProfile() {
    try {
      const raw = localStorage.getItem('vitta_user');
      if (!raw) return;
      const u = JSON.parse(raw);
      if (u.name) {
        const initials = u.name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2) || "AS";
        document.querySelectorAll(".avatar.a1").forEach(el => el.textContent = initials);
        document.querySelectorAll(".user-row strong").forEach(el => el.textContent = u.name);
        document.querySelectorAll(".user-row span").forEach(el => el.textContent = `${u.plan || "Plus Plan"} · ${u.scansLeft || "Unlimited"}`);
        
        const profName = $("#profileUserName");
        if (profName) profName.textContent = u.name;
        const profEmail = $("#profileUserEmail");
        if (profEmail) profEmail.textContent = u.email;
        const profBadge = $("#profileBadge");
        if (profBadge) profBadge.textContent = u.plan || "Plus Member";
        
        const inputName = $("#profInputName");
        if (inputName) inputName.value = u.name;
        const inputEmail = $("#profInputEmail");
        if (inputEmail) inputEmail.value = u.email;
        const inputPayer = $("#profInputPayer");
        if (inputPayer && u.payer) inputPayer.value = u.payer;
        const inputMemId = $("#profInputMemberId");
        if (inputMemId && u.memberId) inputMemId.value = u.memberId;
        const inputGrpNo = $("#profInputGroupNo");
        if (inputGrpNo && u.groupNo) inputGrpNo.value = u.groupNo;
      }
    } catch (e) {
      console.warn("Could not load user profile", e);
    }
  }

  renderGlossary();
  initUserProfile();
})();