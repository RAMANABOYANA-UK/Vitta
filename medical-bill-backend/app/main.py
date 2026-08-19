"""
FastAPI application entry point for the medical bill analysis platform.
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.routes import auth, documents, health
from app.config import settings
from app.database import AsyncSessionLocal, init_db
from app.models import Document
from app.schemas import DocumentStatus

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO if settings.ENVIRONMENT == "development" else logging.WARNING,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

APP_VERSION = "0.3.0"


async def sweep_stuck_documents(max_age_minutes: int = 30) -> int:
    """
    On startup, mark any documents stuck in `processing` for longer than
    `max_age_minutes` as `error` so they are never permanently stuck.

    Returns the number of documents marked as error.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    marked = 0
    try:
        async with AsyncSessionLocal() as session:
            statement = select(Document).where(
                Document.status == DocumentStatus.processing.value,
                Document.updated_at < cutoff,
            )
            result = await session.execute(statement)
            stuck_docs = result.scalars().all()
            for doc in stuck_docs:
                doc.status = DocumentStatus.error.value
                doc.error_message = "Stuck processing timeout"
                session.add(doc)
                marked += 1
            if marked:
                await session.commit()
                logger.warning(
                    "Startup sweep: marked %d stuck document(s) as error",
                    marked,
                )
            else:
                logger.info("Startup sweep: no stuck documents found")
    except Exception:
        logger.exception("Startup sweep failed")
    return marked


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize DB on startup, clean up on shutdown."""
    logger.info("Starting medical bill backend (env=%s)", settings.ENVIRONMENT)
    try:
        await init_db()
        logger.info("Database initialized")
        # Recover stuck documents from previous runs
        await sweep_stuck_documents()
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

# In development, allow all origins. In production, restrict to known frontends.
ALLOWED_ORIGINS = ["*"] if settings.ENVIRONMENT == "development" else [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://app.medbills.example.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(auth.router)


@app.get("/", tags=["root"])
async def root() -> dict:
    """Root endpoint with basic API info."""
    return {
        "name": "Medical Bill Analysis API",
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }