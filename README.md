# Vitta

**AI-powered medical bill analysis and appeal platform**

Vitta turns messy medical bills and Explanations of Benefits (EOBs) into clear, structured insights. It detects billing errors, estimates fair prices, predicts appeal success, and generates grounded, ready-to-use appeal letters.

This is not a simple LLM wrapper. It is a layered system that prioritizes correctness, auditability, and user trust.

## Vision

Help patients and advocates understand medical bills, catch overcharges, and take action — with explanations and letters they can actually trust.

## What Vitta Does

1. **Ingests** medical bills (text-layer PDFs today; images & scanned PDFs once OCR is configured — see Current Status below)
2. **Extracts** line items, CPT/HCPCS codes, ICD-10 codes, amounts, and denial reasons
3. **Validates** codes and reconciles amounts
4. **Detects errors** such as duplicates, unbundling, math mistakes, and price anomalies
5. **Predicts** the likelihood of a successful appeal
6. **Explains** the findings in plain language
7. **Generates** a grounded appeal letter that only uses verified claim facts
8. **Verifies** the letter programmatically before the user sees it

## Current Status

This codebase is under active development and is **not yet ready for real,
un-de-identified patient bills.** The layered architecture (deterministic rules +
ML scoring + grounded, verified letter generation) and the Auth/PHI gate
(opaque revocable tokens, per-document ownership, audit trail) are in place and
test-passing, but several production-gating pieces are still pending:

- **Images & scanned PDFs** require a configured OCR provider (`OCR_ENABLED`);
  until then those uploads fail honestly (they are not silently fabricated).
- **Pricing benchmarks & model training** currently use synthetic data; the
  reported accuracy/AUC are train/test numbers on that synthetic distribution,
  **not** real-claim performance.
- **Email delivery** is a dev-safe "log instead of send" boundary until a real
  transactional/SMTP sender is wired.
- Real-bill collection, model retraining on real labels, and a durable
  distributed rate limit are future work.

## System Architecture

```
Upload (PDF with text layer today; images/scanned PDFs once OCR is configured)
        ↓
Document Understanding & Extraction
  - Text extraction from the PDF text layer (pypdf)
  - Image / scanned-PDF OCR (behind the OCR_ENABLED flag)
  - Structured extraction of codes, amounts, and entities
  - Code validation (CPT / ICD-10)
  - Amount reconciliation
        ↓
Intelligence Layer
  - Deterministic rules (duplicates, unbundling, math errors)
  - Pricing anomaly detection
  - Appeal success prediction
  - Explainable signals (including SHAP-style contributions)
        ↓
Grounded Generation
  - Plain-language explanation
  - Appeal letter generation constrained to verified facts
  - Programmatic verification of every number, code, and date
        ↓
User Experience
  - Clear analysis results
  - Flag explanations
  - Editable, verified appeal letter
  - Tracking and next actions
```

## Core Principles

1. **Correctness over flash**  
   Numbers and codes must be validated, not hallucinated.

2. **Deterministic rules first**  
   High-confidence errors (duplicates, unbundling, arithmetic issues) are handled by rules, not by an LLM.

3. **Grounded generation**  
   Appeal letters may only use facts present in the structured bill. Every letter is programmatically verified.

4. **Explicit uncertainty**  
   Low-confidence extractions and unverified fields are flagged, never silently passed through.

5. **Graceful degradation**  
   If a downstream service is unavailable, the system continues safely instead of failing hard.

6. **Auditability**  
   Intermediate structured outputs are preserved so every decision can be inspected.

## Monorepo Structure

```
Vitta/
├── frontend/                      # All UI (HTML, CSS, JS)
├── medical-bill-backend/          # Member 3 API + pipeline + letters
├── data-extraction-service/       # Member 2 extraction + ML
├── bill_rules/                    # Member 3 Rust rules engine
├── README.md
└── .gitignore
```

## Services

### Frontend (`frontend/`)
Static HTML, CSS, and JS. Open `index.html` directly in a browser, or serve with any HTTP server:
```bash
cd frontend
python -m http.server 8080
```
See `frontend/README.md` for details.

### Main Backend (`medical-bill-backend`)
- FastAPI
- Document upload and storage
- Pipeline orchestration
- Integration with the rules engine
- Grounded letter generation and verification
- Letter editing endpoint

**Default port:** `8000`

### Rules Engine (`bill_rules`)
- Rust + Axum
- Deterministic checks:
  - Duplicate charges
  - Amount reconciliation
  - NCCI-style unbundling
- Preserves unknown fields for schema evolution

**Default port:** `3001`

### Data Extraction & ML (`data-extraction-service`)
- FastAPI
- Structured extraction (LLM + heuristic fallback)
- CPT/ICD-10 validation
- Pricing anomaly model
- Appeal success model
- Explainable outputs

**Recommended port:** `8001`

## Shared Contract: `ParsedBill`

The central data object shared across the system:

- Document metadata (patient, provider, payer, service date)
- Line items (CPT/HCPCS, ICD-10, amounts, modifiers, flags)
- Totals
- Denial codes
- Appeal prediction
- Plain-language explanation
- Grounded appeal letter
- Audit information

All services must respect this contract.

## Main API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/documents/upload` | Upload a bill or EOB |
| `GET`  | `/api/v1/documents/{id}` | Get document and analysis result |
| `GET`  | `/api/v1/documents/{id}/status` | Get processing status |
| `PATCH`| `/api/v1/documents/{id}/letter` | Edit and re-verify the appeal letter |
| `GET`  | `/health` | Service health |

## Quick Start (Local)

### 1. Rules Engine
```bash
cd bill_rules
cargo run
# http://localhost:3001
```

### 2. Member 2 Extraction Service
```bash
cd data-extraction-service
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

### 3. Main Backend
```bash
cd medical-bill-backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend
```bash
cd frontend
python -m http.server 8080
# http://localhost:8080
```

## Design Philosophy

Vitta is built as a hybrid system:

- Classical rules and validation for high-confidence correctness
- Machine learning for pricing anomalies and appeal odds
- Constrained LLMs only for language generation, always checked against structured data

This combination is what makes the product trustworthy in a high-stakes domain involving money and health data.
