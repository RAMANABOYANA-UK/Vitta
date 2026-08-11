/* ============================================================
   VITTA — App Dashboard Logic
   ============================================================ */

(function () {
  "use strict";

  /* ==========================================================
     MOCK DATA
     ========================================================== */

  const SAMPLE_ER = {
    id: "er",
    name: "Emergency room visit",
    provider: "St. Mary's Medical Center",
    insurer: "BlueCross Shield TX",
    claim: "2025-8841",
    serviceDate: "Jan 22, 2026",
    totalBilled: 7842.5,
    fairLow: 3100,
    fairHigh: 4200,
    overcharge: 2940,
    successChance: 84,
    paid: null, // not yet paid
    lineItems: [
      { date: "01/22/26", code: "99283", desc: "Emergency dept visit, level 3", qty: 1, amount: 1450.0, issue: 1 },
      { date: "01/22/26", code: "99284", desc: "Emergency dept visit, level 4 (unbundled)", qty: 1, amount: 1120.0, issue: 1 },
      { date: "01/22/26", code: "99285", desc: "Emergency dept visit, level 5 (upcoded)", qty: 1, amount: 890.0, issue: 2 },
      { date: "01/22/26", code: "93005", desc: "Electrocardiogram, routine", qty: 1, amount: 320.0, issue: null },
      { date: "01/22/26", code: "81003", desc: "Urinalysis, automated", qty: 1, amount: 145.0, issue: null },
      { date: "01/22/26", code: "80048", desc: "Metabolic panel (duplicate)", qty: 2, amount: 930.0, issue: 3 },
      { date: "01/22/26", code: "99221", desc: "Initial hospital care, low complexity", qty: 1, amount: 1040.0, issue: null },
      { date: "01/22/26", code: "J1200", desc: "Dexamethasone sodium phosphate 1mg", qty: 12, amount: 240.0, issue: null },
      { date: "01/22/26", code: "J0202", desc: "Alteplase, thrombolytic therapy", qty: 1, amount: 1870.5, issue: null },
      { date: "01/22/26", code: "A0428", desc: "Ambulance, BLS, non-emergency", qty: 1, amount: 837.0, issue: null },
    ],
    issues: [
      {
        id: 1,
        title: "Unbundled procedure codes",
        severity: "high",
        tone: "red",
        amount: 1120,
        confidence: "94% confidence",
        desc: "CPT 99283 was billed together with CPT 99284 for the same visit. These codes are mutually exclusive — billing both is a frequent unbundling error.",
        whatHappened: "Two emergency department codes billed for one visit",
        howToFix: "Request the provider re-bill as a single, correct-level visit code (99284).",
        evidence: "CPT 99283 & 99284 are mutually exclusive per CPT guidelines.",
        code: "99283 / 99284",
      },
      {
        id: 2,
        title: "Possible upcoding",
        severity: "high",
        tone: "amber",
        amount: 890,
        confidence: "87% confidence",
        desc: "A Level-5 emergency visit (99285) was billed, but the documented care supports only a Level-4 code (99284). This is a classic upcoding pattern.",
        whatHappened: "Level-5 visit billed, documentation supports Level-4",
        howToFix: "Ask your provider to review the chart and correct the code to Level-4.",
        evidence: "Medical record shows 30-minute visit with no complex decision-making.",
        code: "99285 → 99284",
      },
      {
        id: 3,
        title: "Duplicate charge",
        severity: "medium",
        tone: "blue",
        amount: 930,
        confidence: "91% confidence",
        desc: "The metabolic panel (CPT 80048) was billed twice (qty 2) on the same date for the same patient. The second charge is a duplicate.",
        whatHappened: "Lab panel billed twice on the same visit",
        howToFix: "Request removal of the duplicate line item from the bill.",
        evidence: "Two identical 80048 line items on the same date of service.",
        code: "80048 ×2",
      },
    ],
    actions: [
      { id: "a1", done: true, title: "Request itemized bill", sub: "Ask St. Mary's for a full itemized statement", deadline: "Done", tone: "safe" },
      { id: "a2", done: false, title: "Call provider billing office", sub: "Ask them to correct the unbundled codes", deadline: "3 days", tone: "warn" },
      { id: "a3", done: false, title: "Draft & file internal appeal", sub: "Internal appeal to BlueCross Shield TX", deadline: "14 days", tone: "urgent" },
      { id: "a4", done: false, title: "File external review", sub: "Independent review if internal appeal is denied", deadline: "Est. 30 days", tone: "safe" },
    ],
    deadlineText: "14 days to appeal deadline",
    strategies: [
      { id: "unbundling", title: "Unbundling correction", desc: "Codes were billed separately when they should be one. Strongest angle with " + "84" + "% success." },
      { id: "upcoding", title: "Upcoding dispute", desc: "Documentation supports a lower code. Cite the chart review." },
      { id: "duplicate", title: "Duplicate charge removal", desc: "The same lab was billed twice. Request a credit." },
    ],
    appealFacts: [
      "<strong>Strong precedent:</strong> 78% of similar unbundling cases were overturned in your state.",
      "<strong>Deadline:</strong> You have <strong>14 days</strong> left to file an internal appeal.",
      "<strong>Draft ready:</strong> Your appeal letter is pre-written and ready to edit.",
    ],
    ascNote: "Based on 1,240 similar cases in your state.",
    ascFacts: [
      "Unbundling is a strong appeal angle",
      "Your state overturned 78% of similar cases",
      "Deadline: 14 days remaining",
    ],
    timeline: [
      { title: "Bill uploaded", date: "Today", desc: "Your ER bill was analyzed by Vitta.", state: "done" },
      { title: "Request itemized bill", date: "Today", desc: "Ask St. Mary's for a full itemized statement.", state: "done" },
      { title: "Call provider billing office", date: "In 3 days", desc: "Ask them to correct the unbundled codes.", state: "current" },
      { title: "File internal appeal", date: "In 14 days", desc: "Send appeal to BlueCross Shield TX.", state: "pending" },
      { title: "External review", date: "If needed", desc: "Independent review if internal appeal is denied.", state: "pending" },
    ],
    plainSummary:
      "You were billed $7,842.50 for an emergency room visit on January 22. Based on 40 million similar claims, a fair price for this level of care is between $3,100 and $4,200. Vitta found 3 likely billing errors — unbundled codes, possible upcoding, and a duplicate lab charge — totaling an estimated $2,940 in overcharges. Your appeal success chance is 84%, and you have 14 days left to file an internal appeal.",
  };

  /* -------- Sample variants (surgery & EOB) reuse the ER structure with tweaks -------- */

  const SAMPLE_SURGERY = {
    ...SAMPLE_ER,
    id: "surgery",
    name: "Outpatient surgery",
    provider: "Lakeside Surgery Center",
    insurer: "UnitedHealth PPO",
    claim: "2026-1193",
    serviceDate: "Feb 3, 2026",
    totalBilled: 12480.0,
    fairLow: 6900,
    fairHigh: 8200,
    overcharge: 4210,
    successChance: 71,
    lineItems: [
      { date: "02/03/26", code: "29881", desc: "Arthroscopy, knee, medial meniscectomy", qty: 1, amount: 3850.0, issue: null },
      { date: "02/03/26", code: "G0463", desc: "Hospital outpatient clinic visit", qty: 1, amount: 640.0, issue: null },
      { date: "02/03/26", code: "A4550", desc: "Surgical tray (inflated)", qty: 1, amount: 980.0, issue: 1 },
      { date: "02/03/26", code: "J7326", desc: "Hyaluronan injection (out of network)", qty: 1, amount: 2100.0, issue: 2 },
      { date: "02/03/26", code: "99213", desc: "Office visit, level 3", qty: 1, amount: 320.0, issue: null },
      { date: "02/03/26", code: "73562", desc: "X-ray, knee, 3 views", qty: 1, amount: 410.0, issue: null },
      { date: "02/03/26", code: "J2001", desc: "Lidocaine injection", qty: 2, amount: 180.0, issue: null },
      { date: "02/03/26", code: "A0428", desc: "Facility fee (inflated)", qty: 1, amount: 4000.0, issue: 3 },
    ],
    issues: [
      {
        id: 1,
        title: "Inflated supply charge",
        severity: "high",
        tone: "red",
        amount: 640,
        confidence: "89% confidence",
        desc: "The surgical tray (A4550) was billed at $980 — the fair price for this item is typically $340 or less.",
        whatHappened: "Surgical tray billed well above market rate",
        howToFix: "Request the facility re-price the supply charge to the market rate.",
        evidence: "Fair price data: A4550 median cost is $340.",
        code: "A4550",
      },
      {
        id: 2,
        title: "Out-of-network surprise",
        severity: "medium",
        tone: "amber",
        amount: 2100,
        confidence: "93% confidence",
        desc: "An out-of-network provider administered the hyaluronan injection at an in-network facility. This may be protected under the No Surprises Act.",
        whatHappened: "Out-of-network provider at in-network facility",
        howToFix: "Dispute balance bill citing the No Surprises Act; you should pay only the in-network cost-share.",
        evidence: "No Surprises Act §2799B-2 protects against surprise out-of-network billing.",
        code: "J7326",
      },
      {
        id: 3,
        title: "Facility fee inflated",
        severity: "medium",
        tone: "blue",
        amount: 1470,
        confidence: "82% confidence",
        desc: "The facility fee of $4,000 is well above the fair range for this outpatient procedure ($2,300–$2,800).",
        whatHappened: "Facility fee above fair market range",
        howToFix: "Negotiate the facility fee using the fair-price comparison.",
        evidence: "Similar outpatient arthroscopy facility fees average $2,500.",
        code: "Facility fee",
      },
    ],
    actions: [
      { id: "a1", done: true, title: "Request itemized bill", sub: "Ask Lakeside for a full itemized statement", deadline: "Done", tone: "safe" },
      { id: "a2", done: false, title: "Dispute balance bill (No Surprises Act)", sub: "File dispute with your insurer", deadline: "7 days", tone: "warn" },
      { id: "a3", done: false, title: "Negotiate facility fee", sub: "Use fair-price comparison talking points", deadline: "10 days", tone: "warn" },
      { id: "a4", done: false, title: "Draft & file internal appeal", sub: "Internal appeal to UnitedHealth PPO", deadline: "21 days", tone: "safe" },
    ],
    deadlineText: "21 days to appeal deadline",
    strategies: [
      { id: "supply", title: "Inflated supply charge", desc: "Surgical tray was billed at $980 vs. a market rate of ~$340. Strongest angle with " + "71" + "% success." },
      { id: "surprise", title: "No Surprises Act dispute", desc: "Out-of-network provider at an in-network facility. Cite the statute." },
      { id: "facility", title: "Facility fee negotiation", desc: "Compare the $4,000 fee against the fair range and negotiate down." },
    ],
    appealFacts: [
      "<strong>Strong precedent:</strong> 72% of similar balance-billing disputes were overturned in your state.",
      "<strong>Deadline:</strong> You have <strong>7 days</strong> to file a No Surprises Act dispute.",
      "<strong>Draft ready:</strong> Your negotiation script is pre-written and ready to use.",
    ],
    ascNote: "Based on 980 similar cases in your state.",
    ascFacts: [
      "No Surprises Act is a strong appeal angle",
      "Your state overturned 72% of similar disputes",
      "Deadline: 7 days to file dispute",
    ],
    timeline: [
      { title: "Bill uploaded", date: "Today", desc: "Your surgery bill was analyzed by Vitta.", state: "done" },
      { title: "Request itemized bill", date: "Today", desc: "Ask Lakeside for a full itemized statement.", state: "done" },
      { title: "Dispute balance bill", date: "In 7 days", desc: "File a No Surprises Act dispute.", state: "current" },
      { title: "Negotiate facility fee", date: "In 10 days", desc: "Use fair-price talking points.", state: "pending" },
      { title: "File internal appeal", date: "In 21 days", desc: "Send appeal to UnitedHealth PPO.", state: "pending" },
    ],
    plainSummary:
      "You were billed $12,480 for outpatient knee surgery on February 3. The fair price for this procedure is between $6,900 and $8,200. Vitta found 3 issues — an inflated supply charge, an out-of-network surprise covered by the No Surprises Act, and an inflated facility fee — totaling an estimated $4,210 in overcharges. Your appeal success chance is 71%.",
  };

  const SAMPLE_EOB = {
    ...SAMPLE_ER,
    id: "eob",
    name: "Denied EOB",
    provider: "Dr. Elena Marsh, MD",
    insurer: "Aetna HMO",
    claim: "2026-5527",
    serviceDate: "Feb 18, 2026",
    totalBilled: 2950.0,
    fairLow: 1800,
    fairHigh: 2300,
    overcharge: 0, // denial focus
    successChance: 68,
    lineItems: [
      { date: "02/18/26", code: "99214", desc: "Office visit, level 4", qty: 1, amount: 420.0, issue: null },
      { date: "02/18/26", code: "J0597", desc: "Cytokine inhibitor (denied)", qty: 1, amount: 2530.0, issue: 1 },
    ],
    issues: [
      {
        id: 1,
        title: "Claim denied: 'Not medically necessary'",
        severity: "high",
        tone: "red",
        amount: 2530,
        confidence: "Denial reason",
        desc: "Your insurer denied coverage for the cytokine inhibitor (J0597), claiming it is not medically necessary. Your provider certified it as medically necessary.",
        whatHappened: "Claim denied as 'not medically necessary'",
        howToFix: "File an internal appeal with a letter of medical necessity from your provider.",
        evidence: "Provider certification + clinical documentation attached.",
        code: "J0597",
      },
    ],
    actions: [
      { id: "a1", done: true, title: "Review denial reason", sub: "Identified as 'not medically necessary'", deadline: "Done", tone: "safe" },
      { id: "a2", done: false, title: "Get letter of medical necessity", sub: "Ask Dr. Marsh for a supporting letter", deadline: "5 days", tone: "warn" },
      { id: "a3", done: false, title: "File internal appeal", sub: "Internal appeal to Aetna HMO", deadline: "18 days", tone: "urgent" },
      { id: "a4", done: false, title: "Request external review", sub: "If internal appeal is denied", deadline: "Est. 45 days", tone: "safe" },
    ],
    deadlineText: "18 days to appeal deadline",
    strategies: [
      { id: "necessity", title: "Letter of medical necessity", desc: "Your provider certified the drug as medically necessary — a strong rebuttal." },
      { id: "policy", title: "Use Your state's external review", desc: "If internal appeal is denied, request an independent external review." },
      { id: "documentation", title: "Cite clinical documentation", desc: "Attach provider notes and treatment history to support the appeal." },
    ],
    appealFacts: [
      "<strong>Provider support:</strong> Your provider certified the procedure as medically necessary.",
      "<strong>Deadline:</strong> You have <strong>18 days</strong> left to file an internal appeal.",
      "<strong>Letter ready:</strong> A draft appeal with the medical-necessity argument is ready to edit.",
    ],
    ascNote: "Based on 760 similar medical-necessity denials in your state.",
    ascFacts: [
      "Medical necessity is a strong appeal angle",
      "Provider certification supports your case",
      "Deadline: 18 days remaining",
    ],
    timeline: [
      { title: "EOB uploaded", date: "Today", desc: "Your Explanation of Benefits was analyzed.", state: "done" },
      { title: "Review denial reason", date: "Today", desc: "Denial identified as 'not medically necessary'.", state: "done" },
      { title: "Get letter of medical necessity", date: "In 5 days", desc: "Ask Dr. Marsh for a supporting letter.", state: "current" },
      { title: "File internal appeal", date: "In 18 days", desc: "Send appeal to Aetna HMO.", state: "pending" },
      { title: "External review", date: "If needed", desc: "Independent review if internal appeal is denied.", state: "pending" },
    ],
    plainSummary:
      "Your insurer denied a $2,530 injection benefit, saying it was 'not medically necessary.' Your provider certified it as medically necessary, which gives you a strong basis to appeal. Vitta estimates your appeal success chance at 68%. You have 18 days to file an internal appeal.",
  };

  const SAMPLES = {
    er: SAMPLE_ER,
    surgery: SAMPLE_SURGERY,
    eob: SAMPLE_EOB,
  };

  /* -------- Glossary -------- */
  const GLOSSARY = [
    { code: "99283", type: "CPT", meaning: "Emergency department visit, level 3 — a moderate-complexity ER visit." },
    { code: "99284", type: "CPT", meaning: "Emergency department visit, level 4 — a high-complexity ER visit." },
    { code: "99285", type: "CPT", meaning: "Emergency department visit, level 5 — the highest-complexity ER visit." },
    { code: "99213", type: "CPT", meaning: "Office visit, level 3 — a typical established patient visit." },
    { code: "99214", type: "CPT", meaning: "Office visit, level 4 — a more complex established patient visit." },
    { code: "93005", type: "CPT", meaning: "Electrocardiogram (ECG/EKG), routine tracing only." },
    { code: "80048", type: "CPT", meaning: "Basic metabolic panel — a set of 8 common blood chemistry tests." },
    { code: "81003", type: "CPT", meaning: "Urinalysis, automated — a routine urine test." },
    { code: "29881", type: "CPT", meaning: "Knee arthroscopy with partial meniscectomy — keyhole knee surgery." },
    { code: "73562", type: "CPT", meaning: "X-ray of the knee, 3 views." },
    { code: "J1200", type: "HCPCS", meaning: "Dexamethasone injection — an anti-inflammatory steroid." },
    { code: "J0202", type: "HCPCS", meaning: "Alteplase — a clot-busting medication for blood clots." },
    { code: "J7326", type: "HCPCS", meaning: "Hyaluronan injection — a joint lubricant for knee arthritis." },
    { code: "A0428", type: "HCPCS", meaning: "Ambulance service, basic life support (BLS), non-emergency." },
    { code: "A4550", type: "HCPCS", meaning: "Surgical tray — the sterile supplies used during a procedure." },
    { code: "G0463", type: "HCPCS", meaning: "Hospital outpatient clinic visit for evaluation and management." },
    { code: "99221", type: "CPT", meaning: "Initial hospital inpatient care, low complexity." },
    { code: "Z00.00", type: "ICD-10", meaning: "General adult medical examination without abnormal findings." },
    { code: "E11.9", type: "ICD-10", meaning: "Type 2 diabetes mellitus without complications." },
    { code: "I10", type: "ICD-10", meaning: "Essential (primary) hypertension." },
    { code: "Upcoding", type: "Term", meaning: "Billing a more expensive code than the care actually provided." },
    { code: "Unbundling", type: "Term", meaning: "Billing separate codes for services that should be billed as one." },
    { code: "Balance billing", type: "Term", meaning: "Billing you for the difference between the provider's charge and what insurance paid." },
    { code: "EOB", type: "Term", meaning: "Explanation of Benefits — the statement from your insurer showing what was covered." },
    { code: "Deductible", type: "Term", meaning: "The amount you pay out of pocket before your insurance starts paying." },
    { code: "Coinsurance", type: "Term", meaning: "Your share of covered costs after the deductible, usually a percentage." },
    { code: "Copay", type: "Term", meaning: "A fixed amount you pay for a covered service." },
    { code: "No Surprises Act", type: "Term", meaning: "A federal law protecting you from most surprise out-of-network bills for emergency care and at in-network facilities." },
  ];

  /* ==========================================================
     STATE
     ========================================================== */

  let currentData = null;
  let currentIssueFilter = "all";

  /* ==========================================================
     HELPERS
     ========================================================== */

  const $ = (sel) => document.querySelector(sel);
  const money = (n) => "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const money0 = (n) => "$" + n.toLocaleString("en-US", { maximumFractionDigits: 0 });

  const ICONS = {
    alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
    up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9 16H3l9-16z"/><path d="M12 10v4M12 17h.01"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>',
    shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 4v5c0 4.6-3 7.6-7 9-4-1.4-7-4.4-7-9V7l7-4z"/><path d="M9 12l2 2 4-4.5"/></svg>',
  };

  const TONE_CLASS = { red: "tone-red", amber: "tone-amber", blue: "tone-blue", teal: "tone-teal" };
  const SEV_ICON = { high: ICONS.alert, medium: ICONS.up, low: ICONS.clock };

  /* ==========================================================
     NAVIGATION
     ========================================================== */

  const PAGE_META = {
    welcome: { title: "Welcome back, Alex", sub: "Let's find out if your bill is correct." },
    scan: { title: "Analyzing your bill", sub: "Vitta is extracting every line item, code, and amount." },
    overview: { title: "Claim overview", sub: "Everything Vitta found on your bill, at a glance." },
    bill: { title: "Bill detail", sub: "Every line item, decoded and explained in plain language." },
    issues: { title: "Issues found", sub: "Potential billing errors and overcharges detected by Vitta's AI." },
    appeal: { title: "Appeal center", sub: "Your success score, strategy, and a ready-to-edit appeal letter." },
    actions: { title: "Action tracker", sub: "Your step-by-step plan with deadlines and document templates." },
    glossary: { title: "Code glossary", sub: "Common medical codes, translated into plain English." },
    settings: { title: "Settings", sub: "Manage your account, privacy, and preferences." },
  };

  function showPage(page) {
    if (!PAGE_META[page]) return;
    document.querySelectorAll(".page-section").forEach((s) => s.classList.remove("active"));
    const target = $("#page-" + page);
    if (target) target.classList.add("active");
    document.querySelectorAll(".nav-item").forEach((n) => {
      n.classList.toggle("active", n.dataset.page === page);
    });
    $("#topbarTitle").textContent = PAGE_META[page].title;
    $("#topbarSub").textContent = PAGE_META[page].sub;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => {
      const page = item.dataset.page;
      if ((page === "overview" || page === "bill" || page === "issues" || page === "appeal" || page === "actions") && !currentData) {
        showToast("Analyze a bill first to see this view.");
        return;
      }
      showPage(page);
    });
  });

  /* ==========================================================
     SCAN WIZARD
     ========================================================== */

  function startScan(sampleKey) {
    currentData = SAMPLES[sampleKey] || SAMPLE_ER;
    showPage("scan");

    const fill = $("#scanRingFill");
    const pct = $("#scanPct");
    const steps = [1, 2, 3, 4, 5].map((i) => $("#scanStep" + i));
    const CIRC = 103.67;

    // Reset
    steps.forEach((s) => { s.classList.remove("done", "active"); });
    fill.style.strokeDashoffset = CIRC;
    pct.textContent = "0%";

    let progress = 0;
    const tick = () => {
      progress += Math.random() * 9 + 5;
      if (progress > 100) progress = 100;
      const offset = CIRC - (CIRC * progress) / 100;
      fill.style.strokeDashoffset = offset;
      pct.textContent = Math.round(progress) + "%";

      steps.forEach((s, idx) => {
        const stepStart = (idx / steps.length) * 100;
        const stepEnd = ((idx + 1) / steps.length) * 100;
        s.classList.remove("done", "active");
        if (progress >= stepEnd) s.classList.add("done");
        else if (progress >= stepStart) s.classList.add("active");
      });

      if (progress < 100) {
        setTimeout(tick, 260 + Math.random() * 220);
      } else {
        setTimeout(() => {
          steps.forEach((s) => s.classList.add("done"));
          renderAll();
          showPage("overview");
          showToast("Analysis complete — " + currentData.issues.length + " issues found.");
        }, 450);
      }
    };
    setTimeout(tick, 400);
  }

  /* ==========================================================
     RENDERERS
     ========================================================== */

  function renderAll() {
    if (!currentData) return;
    renderBillHeader();
    renderTabCounts();
    renderKPIs();
    renderOverviewIssues();
    renderOverviewActions();
    renderLineItems();
    renderExplanations();
    renderPlainSummary();
    renderIssuesList();
    renderStrategies();
    renderAppealMeta();
    renderLetter();
    renderTimeline();
    renderChecklist();
    renderGlossary();
    updateCounts();
  }

  function renderBillHeader() {
    const d = currentData;
    $("#billProvider").textContent = d.provider;
    $("#billServiceDate").textContent = d.serviceDate;
    $("#billClaim").textContent = d.claim;
    $("#billInsurer").textContent = d.insurer;
  }

  function renderTabCounts() {
    const n = currentData.lineItems.length;
    $("#tabLineCount").textContent = n;
    $("#tabExplainCount").textContent = n;
  }

  function renderKPIs() {
    const d = currentData;
    $("#kpiBilled").textContent = money(d.totalBilled);
    $("#kpiOvercharge").textContent = money0(d.overcharge);
    $("#kpiFair").innerHTML = money0(d.fairLow) + "<small>–</small>" + money0(d.fairHigh);
    $("#kpiChance").innerHTML = d.successChance + "<small>%</small>";

    $("#kpiLineNote").textContent = "Across " + d.lineItems.length + " line items";
    $("#kpiIssueNote").innerHTML = '<span class="trend-down">' + d.issues.length + " issues</span> found on this bill";
    const chanceTrend = d.successChance >= 70 ? "High" : (d.successChance >= 55 ? "Moderate" : "Low");
    const trendClass = d.successChance >= 70 ? "trend-up" : (d.successChance >= 55 ? "" : "trend-down");
    $("#kpiChanceNote").innerHTML = '<span class="' + trendClass + '">' + chanceTrend + "</span> — " + (d.successChance >= 70 ? "strong case to appeal" : d.successChance >= 55 ? "reasonable case to appeal" : "weaker case — review carefully");

    const gauge = $("#appealGaugeFill");
    const CIRC = 103.67;
    gauge.style.strokeDashoffset = CIRC - (CIRC * d.successChance) / 100;
    $("#gaugeValue").textContent = d.successChance + "%";
  }

  function renderOverviewIssues() {
    const el = $("#overviewIssues");
    el.innerHTML = currentData.issues
      .map((issue) => `
        <div class="issue-item clickable" data-open-issue="${issue.id}">
          <span class="issue-icon ${TONE_CLASS[issue.tone]}">${SEV_ICON[issue.severity]}</span>
          <div class="issue-body">
            <div class="issue-top">
              <strong>${issue.title}</strong>
              <span class="amount">${money0(issue.amount)}</span>
            </div>
            <div class="issue-desc">${issue.desc}</div>
            <div class="issue-meta">
              <span>${issue.code}</span>
              <span>${issue.confidence}</span>
            </div>
          </div>
        </div>
      `)
      .join("");

    el.querySelectorAll("[data-open-issue]").forEach((row) => {
      row.addEventListener("click", () => { showPage("issues"); });
    });
  }

  function renderOverviewActions() {
    const el = $("#overviewActions");
    const first = currentData.actions.filter((a) => !a.done).slice(0, 3);
    el.innerHTML = first
      .map((a) => `
        <div class="action-item ${a.done ? "done" : ""}">
          <button class="action-check" data-action="${a.id}" aria-label="Mark as done">${ICONS.check}</button>
          <div class="action-body">
            <div class="action-title">${a.title}</div>
            <div class="action-sub">${a.sub}</div>
          </div>
          <span class="action-deadline ${a.tone}">${a.deadline}</span>
        </div>
      `)
      .join("");

    wireActionChecks(el);
  }

  function renderLineItems() {
    const el = $("#lineItemsBody");
    el.innerHTML = currentData.lineItems
      .map((li) => {
        const flagged = li.issue ? `<span class="flag-icon" title="Issue detected">${ICONS.alert}</span>` : "";
        const pillClass = li.issue ? (currentData.issues.find((i) => i.id === li.issue)?.severity === "high" ? "danger" : "warn") : "";
        return `
          <tr>
            <td>${li.date}</td>
            <td><span class="code-pill ${pillClass}">${li.code}</span>${flagged}</td>
            <td class="row-desc">${li.desc}</td>
            <td>${li.qty}</td>
            <td class="num">${money(li.amount)}</td>
          </tr>
        `;
      })
      .join("");
  }

  function renderExplanations() {
    const el = $("#explainList");
    const statusFor = (li) => {
      if (li.issue) {
        const issue = currentData.issues.find((i) => i.id === li.issue);
        return issue && issue.title.includes("denied")
          ? '<span class="status denied">Denied</span>'
          : '<span class="status partial">Flagged</span>';
      }
      return '<span class="status covered">Covered</span>';
    };

    el.innerHTML = currentData.lineItems
      .map((li) => {
        const plain = li.issue
          ? currentData.issues.find((i) => i.id === li.issue)?.whatHappened + " — " + currentData.issues.find((i) => i.id === li.issue)?.howToFix
          : "This service was covered by your plan. You are responsible for your normal cost-sharing amounts (deductible, coinsurance, or copay).";
        return `
          <div class="explain-item">
            <div class="e-code">
              ${li.code}
              ${statusFor(li)}
            </div>
            <div class="e-desc">${li.desc}</div>
            <div class="e-plain">${plain}</div>
          </div>
        `;
      })
      .join("");
  }

  function renderPlainSummary() {
    $("#plainSummaryText").textContent = currentData.plainSummary;
  }

  function renderIssuesList() {
    const el = $("#issuesList");
    const filtered = currentData.issues.filter((i) => currentIssueFilter === "all" || i.severity === currentIssueFilter);

    if (!filtered.length) {
      el.innerHTML = `<div class="dash-card" style="text-align:center; padding:40px;">
        <p style="color:var(--slate-500); font-size:15px;">No issues match this filter.</p>
      </div>`;
      return;
    }

    el.innerHTML = filtered
      .map((issue) => `
        <div class="issue-card">
          <div class="issue-head">
            <div class="issue-head-left">
              <span class="issue-big-icon ${TONE_CLASS[issue.tone]}">${SEV_ICON[issue.severity]}</span>
              <div>
                <h3>${issue.title}</h3>
                <p>${issue.code} · ${issue.confidence}</p>
              </div>
            </div>
            <div class="issue-money">
              <span class="amount">${money0(issue.amount)}</span>
              <span class="confidence">potential savings</span>
            </div>
          </div>
          <div class="issue-details">
            <div class="issue-detail">
              <span>What happened</span>
              <p>${issue.whatHappened}</p>
            </div>
            <div class="issue-detail">
              <span>How to fix it</span>
              <p>${issue.howToFix}</p>
            </div>
            <div class="issue-detail">
              <span>Evidence</span>
              <p>${issue.evidence}</p>
            </div>
            <div class="issue-detail">
              <span>Why it matters</span>
              <p>${issue.desc}</p>
            </div>
          </div>
          <div class="issue-foot">
            <a href="#" class="btn btn-secondary btn-sm" data-draft-for="${issue.id}">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              Draft appeal for this
            </a>
            <a href="#" class="btn btn-secondary btn-sm" data-view-bill="${issue.code}">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
              View in bill
            </a>
          </div>
        </div>
      `)
      .join("");

    el.querySelectorAll("[data-draft-for]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        showPage("appeal");
      });
    });
    el.querySelectorAll("[data-view-bill]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        showPage("bill");
      });
    });
  }

  function renderStrategies() {
    const el = $("#strategyList");
    const strategies = currentData.strategies;
    el.innerHTML = strategies
      .map((s, idx) => `
        <label class="${idx === 0 ? "selected" : ""}">
          <input type="radio" name="strategy" value="${s.id}" ${idx === 0 ? "checked" : ""} />
          <div class="st-body">
            <strong>${s.title}</strong>
            <p>${s.desc}</p>
          </div>
        </label>
      `)
      .join("");

    el.querySelectorAll("label").forEach((label) => {
      label.addEventListener("click", () => {
        el.querySelectorAll("label").forEach((l) => l.classList.remove("selected"));
        label.classList.add("selected");
        showToast("Strategy updated — appeal letter regenerated.");
      });
    });
  }

  function renderLetter() {
    const d = currentData;
    const issuesText = d.issues
      .map((issue, idx) => `${idx + 1}. ${issue.title}\n   ${issue.whatHappened}. Estimated impact: ${money0(issue.amount)}.`)
      .join("\n\n");

    const requests = d.issues
      .map((issue, idx) => `${idx + 1}. Correct the issue described above (${issue.title}).`)
      .join("\n");

    const letter = `Re: Claim #${d.claim} — Request for Reconsideration

To Whom It May Concern,

I am writing to appeal the processing of claim #${d.claim} for services provided by ${d.provider} on ${d.serviceDate}. I believe this claim contains billing errors that have resulted in an overcharge and I am requesting a full review.

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
    $("#letterTextarea").value = letter;
  }

  function renderAppealMeta() {
    const d = currentData;
    $("#ascValue").innerHTML = d.successChance + "<em>%</em>";
    $("#ascNote").textContent = d.ascNote || "Based on similar cases in your state.";
    $("#scoreBarFill").style.width = d.successChance + "%";
    $("#deadlinePillText").textContent = d.deadlineText || "Appeal deadline pending";

    const appealFactsEl = $("#appealFacts");
    const facts = d.appealFacts || [];
    appealFactsEl.innerHTML = facts
      .map((f) => `
        <div class="appeal-fact">
          <span class="fact-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>
          <span>${f}</span>
        </div>
      `)
      .join("");

    const ascFactsEl = $("#ascFacts");
    const ascFacts = d.ascFacts || [];
    ascFactsEl.innerHTML = ascFacts
      .map((f) => `
        <div class="asc-fact">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          ${f}
        </div>
      `)
      .join("");
  }

  function renderTimeline() {
    const el = $("#timeline");
    el.innerHTML = currentData.timeline
      .map((t) => `
        <div class="timeline-item ${t.state}">
          <div class="tl-title">
            ${t.title}
            <span class="tl-date">${t.date}</span>
          </div>
          <div class="tl-desc">${t.desc}</div>
        </div>
      `)
      .join("");
  }

  function renderChecklist() {
    const el = $("#checklist");
    el.innerHTML = currentData.actions
      .map((a) => `
        <div class="action-item ${a.done ? "done" : ""}">
          <button class="action-check" data-action="${a.id}" aria-label="Toggle action">${ICONS.check}</button>
          <div class="action-body">
            <div class="action-title">${a.title}</div>
            <div class="action-sub">${a.sub}</div>
          </div>
          <span class="action-deadline ${a.tone}">${a.deadline}</span>
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
        const action = currentData.actions.find((a) => a.id === id);
        if (action) {
          action.done = !action.done;
          renderOverviewActions();
          renderChecklist();
        }
      });
    });
  }

  function updateActionCount() {
    const remaining = currentData.actions.filter((a) => !a.done).length;
    $("#navActionCount").textContent = remaining;
  }

  function updateCounts() {
    $("#navIssueCount").textContent = currentData.issues.length;
    updateActionCount();
  }

  function renderGlossary(filter = "") {
    const el = $("#glossaryGrid");
    const q = filter.toLowerCase();
    const items = GLOSSARY.filter(
      (g) => !q || g.code.toLowerCase().includes(q) || g.meaning.toLowerCase().includes(q) || g.type.toLowerCase().includes(q)
    );
    el.innerHTML = items
      .map(
        (g) => `
        <div class="glossary-card">
          <div class="g-code">${g.code}</div>
          <span class="g-type">${g.type}</span>
          <p>${g.meaning}</p>
        </div>
      `
      )
      .join("");
  }

  /* ==========================================================
     EVENTS — upload, tabs, filters, actions
     ========================================================== */

  // Upload zone
  const uploadZone = $("#uploadZone");
  const fileInput = $("#fileInput");

  function triggerUpload() {
    fileInput.click();
  }
  uploadZone.addEventListener("click", triggerUpload);
  uploadZone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      triggerUpload();
    }
  });
  $("#heroUploadBtn").addEventListener("click", (e) => { e.preventDefault(); triggerUpload(); });

  ["dragenter", "dragover"].forEach((evt) => {
    uploadZone.addEventListener(evt, (e) => { e.preventDefault(); uploadZone.classList.add("dragover"); });
  });
  ["dragleave", "drop"].forEach((evt) => {
    uploadZone.addEventListener(evt, (e) => { e.preventDefault(); uploadZone.classList.remove("dragover"); });
  });
  uploadZone.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) startScan("er");
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) startScan("er");
    fileInput.value = "";
  });

  // Sample cards
  document.querySelectorAll(".sample-card").forEach((card) => {
    card.addEventListener("click", () => startScan(card.dataset.sample));
  });

  // Bill tabs
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $("#tab-" + btn.dataset.tab).classList.add("active");
    });
  });

  // Severity filter
  document.querySelectorAll(".severity-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".severity-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentIssueFilter = btn.dataset.sev;
      renderIssuesList();
    });
  });

  // Glossary search
  $("#glossarySearch").addEventListener("input", (e) => renderGlossary(e.target.value));

  // Cross-nav buttons
  $("#viewBillBtn").addEventListener("click", (e) => { e.preventDefault(); showPage("bill"); });
  $("#goAppealBtn").addEventListener("click", (e) => { e.preventDefault(); showPage("appeal"); });

  // Appeal letter actions
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

  $("#sendLetterBtn").addEventListener("click", (e) => {
    e.preventDefault();
    showToast("Appeal marked as sent — added to your timeline.");
  });

  $("#shareLetterBtn").addEventListener("click", (e) => {
    e.preventDefault();
    showToast("Secure share link created (expires in 7 days).");
  });

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
      `Insurer: ${d.insurer}`,
      `Claim #: ${d.claim}`,
      `Service date: ${d.serviceDate}`,
      "",
      `Total billed: ${money(d.totalBilled)}`,
      `Fair price range: ${money0(d.fairLow)} – ${money0(d.fairHigh)}`,
      `Likely overcharge: ${money0(d.overcharge)}`,
      `Appeal success chance: ${d.successChance}%`,
      "",
      "ISSUES FOUND:",
      ...d.issues.map((i) => `- ${i.title}: ${money0(i.amount)} (${i.severity})`),
      "",
      d.plainSummary,
    ];
    return lines.join("\n");
  }

  // Upgrade modal
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

  // Delete data
  $("#deleteDataBtn").addEventListener("click", (e) => {
    e.preventDefault();
    showToast("Data deletion initiated — you'll get a confirmation email.");
  });

  // Doc upload
  $("#docUploadRow").addEventListener("click", () => {
    showToast("Document upload started (PDF, JPG, PNG).");
  });

  /* ==========================================================
     TOASTS
     ========================================================== */

  function showToast(message) {
    const container = $("#toastContainer");
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.innerHTML = `${ICONS.check}<span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.classList.add("out");
      setTimeout(() => toast.remove(), 300);
    }, 3200);
  }

  /* ==========================================================
     INIT
     ========================================================== */

  renderGlossary();
})();