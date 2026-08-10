# Medical Bill Analysis Backend

Backend for the AI-powered medical bill analysis platform. This is **Phase 1: Foundation** — it provides a complete, working backend with a mock pipeline so the frontend and other team members can build against real API shapes before the real extraction and Rust rules engine are integrated.

## Tech Stack

- **Python 3.11+**
- **FastAPI** — web framework
- **SQLModel** — ORM (SQLAlchemy + Pydantic)
- **SQLite** (default, zero-setup local dev) or **PostgreSQL** (production, via asyncpg)
- **S3-compatible storage** — local filesystem (default) or S3 (MinIO, AWS, R2)
- **python-multipart** — file uploads

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
│   │       ├── documents.py # Upload, get, status endpoints
│   │       └── health.py    # Health check
│   ├── services/
│   │   ├── storage.py       # Local + S3 storage abstraction
│   │   ├── pipeline.py      # Mock analysis pipeline + status transitions
│   │   └── mock_data.py     # Realistic mock ParsedBill generator
│   └── core/
│       └── security.py      # Storage key generation, filename sanitization
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

### 4. Run the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:

- **Swagger UI:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

## API Endpoints

| Method | Path                              | Description                                    |
|--------|-----------------------------------|------------------------------------------------|
| GET    | `/`                               | API info                                       |
| GET    | `/health`                         | Health check                                   |
| POST   | `/api/v1/documents/upload`        | Upload a medical bill (PDF/image)              |
| GET    | `/api/v1/documents/{id}`          | Get document + analysis result                 |
| GET    | `/api/v1/documents/{id}/status`   | Get document processing status                 |

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

After processing completes (default 3-second mock delay), the response includes the full `result` object with patient, provider, payer, line items, totals, denial codes, appeal prediction, explanation, and the generated appeal letter.

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
```

## Shared Data Contract (ParsedBill)

The `ParsedBill` schema is the single shared contract between the backend, frontend, and ML/rules services:

- `document_id`, `status`, `uploaded_at`, `source_type`
- `patient`, `provider`, `payer` (structured dicts)
- `service_date`
- `line_items` — CPT/HCPCS codes, ICD-10 diagnoses, units, charge/allowed/paid amounts, modifiers, flags
- `totals` — billed, allowed, insurance_paid, patient_responsibility, potential_savings
- `denial_codes`
- `appeal_prediction` — success probability, confidence interval, top factors
- `explanation` — natural-language analysis
- `letter` — markdown appeal letter + verification status
- `audit` — pipeline metadata (engine names, confidence, timing)

## Extension Points (for later phases)

The code is structured so the real pipeline can be dropped in without API changes:

1. **Extraction** — replace `generate_mock_parsed_bill()` in `mock_data.py` with the real OCR/extraction service.
2. **Rules engine** — the Rust rules engine plugs into `pipeline.py` between extraction and prediction.
3. **Letter generation** — replace the template letter in `mock_data.py` with an LLM-generated letter.
4. **Status transitions** — `_ALLOWED_TRANSITIONS` in `pipeline.py` validates all state changes.

## Development Notes

- All DB access is async (SQLAlchemy async engine with aiosqlite/asyncpg).
- Background pipeline tasks open their own DB session (request-scoped sessions are not reused).
- Uploads are validated for content type (PDF, JPEG, PNG, TIFF, WebP) and size (25 MB max).
- Storage keys are UUID-prefixed to prevent collisions and path traversal.

## Troubleshooting

**"Connection refused" on startup** → PostgreSQL isn't running. Run `docker compose up -d`, or switch to SQLite in `.env`.

**"Invalid status transition"** → The pipeline tried to move a document from a terminal state. Check the document's current status.

**S3 errors** → Ensure credentials and bucket name are set in `.env` and the bucket exists.