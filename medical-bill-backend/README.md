# Medical Bill Analysis Backend

Backend for the AI-powered medical bill analysis platform. This is the **Member 3 core** — a complete, production-minded backend with an unbreakable pipeline, full observability, and a safe recovery path.

## Tech Stack

- **Python 3.11+**
- **FastAPI** — web framework
- **SQLModel** — ORM (SQLAlchemy + Pydantic)
- **SQLite** (default, zero-setup local dev) or **PostgreSQL** (production, via asyncpg)
- **S3-compatible storage** — local filesystem (default) or S3 (MinIO, AWS, R2)
- **python-multipart** — file uploads
- **httpx** — async HTTP client for Rust rules engine + Member 2 service

## Architecture (Member 3 Core)

```
Upload
  ↓
[Background Task] — unbreakable state machine
  ↓
Extraction + XGBoost Scoring  ← Member 2 (optional, feature-flagged)
  ↓
Rust Rules Engine             ← deterministic flags (duplicates, math, unbundling)
  ↓
Grounded Letter Generation + Programmatic Verification
  ↓
letter_ready (or error)
```

### Graceful Degradation

| Dependency              | If unavailable                          | Behavior                          |
|-------------------------|-----------------------------------------|-----------------------------------|
| Rust rules engine       | Timeout / connection error              | Continue without deterministic flags |
| Member 2 extraction     | Disabled or unreachable                 | Fall back to high-quality mock    |
| LLM                     | No API key or error                     | Safe template letter              |

The system never crashes the user experience because of a downstream failure.

## Project Structure

```
medical-bill-backend/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Pydantic-settings configuration
│   ├── database.py          # Async SQLAlchemy/SQLModel engine + session
│   ├── models.py            # SQLModel database models
│   ├── schemas.py           # Pydantic schemas (ParsedBill shared contract)
│   ├── api/
│   │   └── routes/
│   │       ├── documents.py # Upload, get, status, letter, reprocess endpoints
│   │       └── health.py    # Health check with dependency status
│   ├── services/
│   │   ├── storage.py       # Local + S3 storage abstraction
│   │   ├── pipeline.py      # Observable pipeline + status transitions + audit
│   │   ├── rules_engine.py  # HTTP client for the Rust bill_rules service
│   │   ├── extraction_client.py  # HTTP client for Member 2 service
│   │   ├── letter_generator.py   # LLM-grounded appeal letter generation
│   │   ├── letter_verifier.py    # Programmatic letter fact verification
│   │   └── mock_data.py     # Realistic mock ParsedBill generator
│   └── core/
│       └── security.py      # Storage key generation, filename sanitization
├── scripts/
│   └── e2e_smoke_test.py    # End-to-end smoke test
├── tests/
│   ├── test_letter_verifier.py
│   └── test_pipeline_status.py
├── requirements.txt
├── .env.example
├── docker-compose.yml       # Local PostgreSQL (optional)
└── README.md
```

## Setup

### 1. Prerequisites

- Python 3.11+
- Optionally: Docker (for local PostgreSQL) or an existing PostgreSQL instance
- Optionally: an S3-compatible bucket (MinIO, AWS S3) for production-style storage
- Optionally: Rust toolchain (for the rules engine)

### 2. Configure environment

```bash
cp .env.example .env
```

The default `.env` uses **SQLite** — zero setup, no database server needed:

```env
DATABASE_URL=sqlite+aiosqlite:///./medical_bills.db
```

For **PostgreSQL** (production), uncomment the PostgreSQL line:

```env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/medical_bills
```

Then start PostgreSQL:

```bash
docker compose up -d
```

### 3. Install dependencies

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

## Running Locally

**Terminal 1 – Rust rules engine**
```bash
cd bill_rules
cargo run
# listens on http://localhost:3001
```

**Terminal 2 – Backend**
```bash
cd medical-bill-backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

**Optional – Member 2 service**
```bash
cd data-extraction-service
# follow its README, run on port 8001
# then set EXTRACTION_SERVICE_ENABLED=true
```

The API will be available at:

- **Swagger UI:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

## API Endpoints

| Method | Path                              | Description                                    |
|--------|-----------------------------------|------------------------------------------------|
| GET    | `/`                               | API info                                       |
| GET    | `/health`                         | Health check with dependency status            |
| POST   | `/api/v1/documents/upload`        | Upload a medical bill (PDF/image)              |
| GET    | `/api/v1/documents/{id}`          | Get document + analysis result                 |
| GET    | `/api/v1/documents/{id}/status`   | Get document processing status                 |
| PATCH  | `/api/v1/documents/{id}/letter`   | Update and re-verify a document's appeal letter|
| POST   | `/api/v1/documents/{id}/reprocess`| Recovery: re-process a stuck/errored document  |

### Uploading a document

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@/path/to/bill.pdf"
```

Response (201 Created):

```json
{
  "id": "a1b2c3d4-...",
  "original_filename": "bill.pdf",
  "storage_key": "5f8a2b7e-.../bill.pdf",
  "content_type": "application/pdf",
  "status": "uploaded",
  "error_message": null,
  "created_at": "2025-01-01T12:00:00Z",
  "updated_at": "2025-01-01T12:00:00Z"
}
```

### Checking status

```bash
curl http://localhost:8000/api/v1/documents/{id}/status
```

Status flow: `uploaded → processing → analyzed → letter_ready` (or `error`).

### Getting the full result

```bash
curl http://localhost:8000/api/v1/documents/{id}
```

After processing completes (default 3-second mock delay), the response includes the full `result` object with patient, provider, payer, line items, totals, denial codes, appeal prediction, explanation, the generated appeal letter, and the **audit trail**.

## Recovery

If a document is stuck in `processing` or ends in `error`:

```bash
curl -X POST http://localhost:8000/api/v1/documents/{id}/reprocess
```

This resets the document to `uploaded` and re-queues the pipeline safely. Only documents in `error` or `processing` can be re-processed — terminal `letter_ready` documents are rejected with a 409.

## Smoke Test

```bash
python scripts/e2e_smoke_test.py
```

This verifies the full journey: health check → upload → processing → letter_ready → audit trail present.

## Health

```bash
curl http://localhost:8000/health
```

Returns overall status (`ok` / `degraded`) plus reachability of the rules engine and extraction service, and LLM configuration.

## Storage Configuration

### Local storage (default)

```env
STORAGE_TYPE=local
LOCAL_STORAGE_PATH=./uploads
```

Files are stored under `./uploads/` with safe, unique keys.

### S3-compatible storage

```env
STORAGE_TYPE=s3
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
S3_BUCKET=medical-bills
```

Works with AWS S3, MinIO, Cloudflare R2, or any S3-compatible endpoint.

## Pipeline Configuration

```env
# Delay simulating the analysis pipeline (seconds)
PIPELINE_DELAY_SECONDS=3.0

# Use the mock pipeline (true) or real extraction (false, not yet implemented)
MOCK_PIPELINE=true

# Rust rules engine
RULES_ENGINE_URL=http://localhost:3001
RULES_ENGINE_TIMEOUT_SECONDS=5.0
RULES_ENGINE_ENABLED=true
```

### Rules engine integration

After the mock (or real) extraction generates a `ParsedBill`, the pipeline sends
the rules-relevant subset (`document_id`, `status`, `service_date`, `line_items`,
`totals`) to the Rust service at `POST /apply-rules`. The response's flags are
merged back into the full bill by line-item id.

The client in `app/services/rules_engine.py` is the **only** place that knows
how to talk to the Rust service. Behavior:

- `RULES_ENGINE_ENABLED=false` → skips the call entirely
- Service unreachable or timeout → logs a warning, returns bill unchanged
- HTTP error (4xx/5xx) → logs the status code, returns bill unchanged
- Unexpected exception → logs the traceback, returns bill unchanged

## Observability & Audit Trail

Every document's journey is recorded in the `audit` object attached to the final `ParsedBill`:

```json
{
  "pipeline_version": "0.3.0",
  "started_at": "2026-08-13T18:08:03+00:00",
  "extraction_path": "mock",
  "rules_engine": {
    "enabled": true,
    "flags_added": 2,
    "status": "applied"
  },
  "scoring": {
    "anomaly_flags": 1,
    "appeal_probability": 0.74,
    "model_version": null
  },
  "letter": {
    "status": "draft",
    "verified_fields_count": 8,
    "verification_passed": true
  },
  "timings_ms": {
    "extraction": 1.9,
    "rules": 12.4,
    "letter": 0.5,
    "total": 14.8
  },
  "completed_at": "2026-08-13T18:08:03+00:00"
}
```

Structured logging at every stage includes `document_id`, stage name, success/failure, and key metrics — so operators can debug any document without reading code.

## Shared Data Contract (ParsedBill)

The `ParsedBill` schema is the single shared contract between the backend, frontend, and ML/rules services:

- `document_id`, `status`, `uploaded_at`, `source_type`
- `patient`, `provider`, `payer` (structured dicts)
- `service_date`
- `line_items` — CPT/HCPCS codes, ICD-10 diagnoses, units, charge/allowed/paid amounts, modifiers, flags
- `totals` — billed, allowed, insurance_paid, patient_responsibility, potential_savings
- `denial_codes`
- `appeal_prediction` — success probability, confidence interval, top factors, model version
- `explanation` — natural-language analysis
- `letter` — markdown appeal letter + verification status
- `audit` — full pipeline audit trail (path, timings, flags, verification)

## Development Notes

- All DB access is async (SQLAlchemy async engine with aiosqlite/asyncpg).
- Background pipeline tasks open their own DB session (request-scoped sessions are not reused).
- Uploads are validated for content type (PDF, JPEG, PNG, TIFF, WebP) and size (25 MB max).
- Storage keys are UUID-prefixed to prevent collisions and path traversal.
- Status transitions are validated against `_ALLOWED_TRANSITIONS` — no hardcoded status strings.
- The error path always commits a terminal `error` status via a fresh session.

## Troubleshooting

**"Connection refused" on startup** → PostgreSQL isn't running. Run `docker compose up -d`, or switch to SQLite in `.env`.

**"Invalid status transition"** → The pipeline tried to move a document from a terminal state. Check the document's current status.

**S3 errors** → Ensure credentials and bucket name are set in `.env` and the bucket exists.

**Document stuck in `processing`** → Use the recovery endpoint:
```bash
curl -X POST http://localhost:8000/api/v1/documents/{id}/reprocess
```

**Rules engine unreachable** → The backend continues without deterministic flags (graceful degradation). Check `GET /health` for the rules engine status.