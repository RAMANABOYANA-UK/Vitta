FROM python:3.11-slim AS base

# Build stage with Rust toolchain (for building/downloading ML deps if needed).
FROM python:3.11-slim AS build
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv

RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Runtime stage — keep the image lean (no build toolchain).
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV=/opt/venv

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY app ./app
COPY models ./models

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]