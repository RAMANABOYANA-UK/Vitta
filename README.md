MedBills — Data Extraction & ML Models Service


The Data Extraction & ML Models microservice for an AI-powered medical bill / EOB (Explanation of Benefits) analysis platform. This service turns raw OCR output into clean, validated, structured ParsedBill data that downstream services (a Rust rules engine and a grounded LLM letter generator) trust without re-checking.

Core rule: never silently pass through an unverified or low-confidence value — flag it explicitly. Downstream services trust the verified field without re-checking it, so it has to be reliable.

What this service does
Extraction — turns raw OCR text + layout JSON (bounding boxes, tables) into a draft ParsedBill using an LLM with schema-constrained output (Instructor) or an offline heuristic fallback. Handles both bill and EOB formats. Preserves provenance (every value points back to its source location) and flags low-confidence regions, multi-page tables, and handwriting rather than guessing.

Validation — checks extracted CPT/HCPCS and ICD-10 codes against CMS/AMA reference data (bundled proxy dataset, extensible to full CMS files), flagging invalid, deprecated, or mismatched codes. Verifies amount reconciliation (charge − allowed = adjustment, allowed − paid = patient responsibility, line-item sums match stated totals). Sets verified: true/false on every code and amount.

Scoring — two XGBoost models with probability calibration (isotonic):

Pricing anomaly model — flags charges anomalous relative to fair-price benchmarks (CPT code, geography, provider type as features).
Appeal-success model — predicts the probability of appeal success.
Both output calibrated probabilities (never raw scores) and SHAP explanations pre-formatted as clean, human-readable key-value contributions for a downstream LLM to quote directly.
Persistence — validated/scored results are written to a shared PostgreSQL database (Neon/Supabase-compatible) when DATABASE_URL is configured.

Tech stack
Python 3.10+
FastAPI — API layer
Pydantic v2 — the ParsedBill contract
Instructor + OpenAI — structured LLM extraction (optional; heuristic fallback included)
XGBoost — ML models
scikit-learn — calibration (CalibratedClassifierCV), metrics
SHAP — explainability
SQLAlchemy + psycopg2 — PostgreSQL persistence
Project structure
medbills/
├── app/
│   ├── __init__.py
│   ├── config.py              # pydantic-settings configuration
│   ├── main.py                # FastAPI app with /extract, /validate, /score
│   ├── db.py                  # PostgreSQL persistence layer
│   ├── models/
│   │   ├── __init__.py
│   │   └── parsed_bill.py     # The ParsedBill contract (Pydantic)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── extractor.py       # Extraction pipeline (LLM + heuristic fallback)
│   │   ├── reference_data.py  # CMS/AMA code reference data
│   │   ├── validation_service.py  # Code & amount validation
│   │   └── scoring_service.py # ML scoring + SHAP explanations
│   └── ml/
│       ├── __init__.py
│       ├── synthetic_data.py  # Synthetic data generator
│       └── models.py          # XGBoost models + calibration + SHAP
├── scripts/
│   └── train_models.py        # Training script
├── tests/
│   ├── test_validation.py     # Mismatched totals, invalid codes
│   ├── test_extraction.py     # Extraction pipeline
│   ├── test_ml.py             # ML models + SHAP
│   └── test_api.py            # FastAPI endpoints
├── requirements.txt
├── .env.example
└── README.md
Setup
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set OPENAI_API_KEY for LLM extraction, DATABASE_URL for persistence

# 4. Train the ML models (on synthetic data)
python -m scripts.train_models
Running the service
uvicorn app.main:app --reload --port 8000
Interactive API docs: http://localhost:8000/docs

API endpoints
Endpoint	Description
GET /health	Health check (LLM configured? DB connected?)
POST /extract	Raw OCR text + layout JSON → draft ParsedBill
POST /validate	Draft ParsedBill → validated ParsedBill (verified flags + warnings)
POST /score	Validated ParsedBill → scored ParsedBill (pricing anomaly + appeal success + SHAP)
POST /pipeline	Convenience: extract → validate → score in one call
Each endpoint is independently callable and retryable.

Example: /extract
{
  "raw_ocr_text": "Provider: City Medical Group\nNPI: 1234567890\n99214 Office visit $200.00\nTotal Billed: $200.00\n",
  "document_id": "doc-123"
}
Example: /validate
{
  "parsed_bill": { "...draft ParsedBill JSON..." }
}
Example: /score
{
  "parsed_bill": { "...validated ParsedBill JSON..." }
}
The ParsedBill contract
The ParsedBill Pydantic model is the shared contract for the whole system. Key sections:

Document metadata — document type (bill/EOB), provider name/NPI, payer, de-identified patient account ref, service date range, statement date
Line items — CPT/HCPCS code, description, ICD-10 codes, modifiers, units, date of service, charge/allowed/paid/patient-responsibility amounts, place of service
Per-field confidence & provenance — OCR confidence, source bounding box/page, verified flag per code/amount
Validation results — which codes passed/failed/ambiguous CMS/AMA lookup
Totals block — billed/allowed/paid/patient-responsibility totals, must satisfy billed − adjustments − paid = patient_responsibility
Pricing anomaly + appeal success — score, calibrated probability, structured SHAP-style explanation
Extraction warnings — low-confidence fields, illegible regions, missing expected fields
Running tests
pytest -v
Tests cover:

Mismatched totals — line-level and document-level reconciliation failures are flagged
Invalid codes — invalid, deprecated, and malformed CPT/ICD-10 codes are flagged, never silently passed
Extraction — bill/EOB parsing, provenance preservation, low-confidence/multi-page/handwriting flagging
ML — model training, calibrated probability output, SHAP explanation structure
API — all endpoints work end-to-end
Notes on correctness
Calibrated probabilities, never raw scores — both models use CalibratedClassifierCV with isotonic regression.
SHAP explanations are pre-formatted — the human_readable field is a clean sentence (e.g., "charge is 3.2x the regional median for CPT 99214") ready for a downstream LLM to quote directly.
Reference data — a small curated proxy dataset of common CPT/HCPCS/ICD-10/modifier codes is bundled for offline operation. To use full CMS data, drop cpt_hcpcs.csv, icd10.csv, and modifiers.csv into data/reference/ (see app/services/reference_data.py for the expected format).
Synthetic training data — real billing data doesn't exist yet, so models are trained on synthetic data matching the schema. The generator has identifiable ground-truth structure so the models learn meaningful patterns.
