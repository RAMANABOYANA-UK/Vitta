# Vitta — medical-bill-backend
# FastAPI backend: uploads, pipeline, grounded letter generation, auth/PHI gate.
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY app ./app

# Runtime config is injected via environment (DATABASE_URL, etc. -> docker-compose).
EXPOSE 8000

# Run with a single worker and thread for the async app; tune for production.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]