"""
FastAPI application entry point for the medical bill analysis platform.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, documents, gateway, health
from app.config import settings
from app.database import init_db

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO if settings.ENVIRONMENT == "development" else logging.WARNING,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize DB on startup, clean up on shutdown."""
    logger.info("Starting medical bill backend (env=%s)", settings.ENVIRONMENT)
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        raise
    yield
    logger.info("Shutting down medical bill backend")


app = FastAPI(
    title="Medical Bill Analysis API",
    description=(
        "Backend for the AI-powered medical bill analysis platform. "
        "Uploads medical bills, runs analysis, and generates appeal letters."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

# Always an explicit allowlist (from settings). A wildcard "*" is invalid
# together with allow_credentials=True — browsers refuse to send the
# Authorization header / credentials to a wildcard origin — so we never use one.
# Configure origins via CORS_ALLOWED_ORIGINS (comma-separated) per environment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(documents.router)
# Additive adapter layer that serves the existing frontend's resource-oriented
# contract (/upload, /jobs, /bills) on top of the document pipeline. Included
# after documents so the canonical /api/v1/documents/* routes take precedence
# for any shared path (there are none today — the gateway uses distinct paths).
app.include_router(gateway.router)


@app.get("/", tags=["root"])
async def root() -> dict:
    """Root endpoint with basic API info."""
    return {
        "name": "Medical Bill Analysis API",
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }