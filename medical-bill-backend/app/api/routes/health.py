"""
Health check endpoint.
"""
from fastapi import APIRouter

from app.config import settings
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])

APP_VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health_check() -> HealthResponse:
    """Basic health check for load balancers and monitoring."""
    return HealthResponse(
        status="ok",
        environment=settings.ENVIRONMENT,
        version=APP_VERSION,
    )