# Vitta Test Suite — Running Tests

## Architecture Note

The Vitta monorepo contains multiple services, each with its own `app` package:

- `medical-bill-backend/app/` → FastAPI backend
- `data-extraction-service/app/` → Extraction and ML service

When pytest discovers tests from the repo root with both services on `pythonpath`, the import `from app.models` can resolve ambiguously. To avoid this, **tests are run with service-specific pytest configurations**.

## Running Tests

### Backend Tests
```bash
# From repo root
python -m pytest -c pytest-backend.ini -q

# Or from service directory (auto-uses local conftest)
cd medical-bill-backend
python -m pytest -q
```

### Extraction Service Tests
```bash
# From repo root
python -m pytest -c pytest-extraction.ini -q

# Or from service directory
cd data-extraction-service
python -m pytest -q
```

### All Tests (Recommended Approach)
```bash
# Run all suites without import collision
python -m pytest -c pytest-backend.ini && python -m pytest -c pytest-extraction.ini
```

### With Verbose Output
```bash
python -m pytest -c pytest-backend.ini -v
python -m pytest -c pytest-extraction.ini -v
```

## Configuration Files

- **`pytest.ini`** — Main config; documents the architecture
- **`pytest-backend.ini`** — Backend service tests only
- **`pytest-extraction.ini`** — Extraction service tests only
- **`conftest.py`** — Root pytest hooks for environment setup (DATABASE_URL, feature flags)

## Environment Variables

The root `conftest.py` automatically sets defaults if not present:

- `DATABASE_URL` — Defaults to `sqlite+aiosqlite:///:memory:` (async in-memory SQLite for tests)
- `EXTRACTION_SERVICE_URL` — Defaults to `http://localhost:8001`
- `RULES_ENGINE_URL` — Defaults to `http://localhost:3001`

Override these by setting them in the environment before running pytest.

## Test Coverage by Service

**Backend** (34 tests)
- Authentication, rate limiting, security
- Pipeline status and processing
- Letter verification and generation
- Frontend adapter integration

**Extraction** (44 tests)
- Feature stability and determinism
- CMS reference data loading
- Extraction and validation
- ML model inference
- API endpoint testing
- Database persistence

## Why Not Run Everything from the Root?

When both `medical-bill-backend/` and `data-extraction-service/` are on Python's import path, a test that does `from app.models import ...` will import from whichever `app` package pytest encounters first. This non-determinism is avoided by using isolated configs per service.

Pytest's `-p conftest` flag ensures that the root conftest.py is always loaded (for environment setup), but the pythonpath is service-specific.
