"""
Health check endpoint with full dependency visibility.

Reports overall service health plus the reachability of the Rust
rules engine and the Member 2 extraction/XGBoost service, so operators
can see at a glance whether any critical dependency is degraded.
"""
import httpx
from fastapi import APIRouter

from app.config import settings
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])

APP_VERSION = "0.3.0"


@router.get("/health", response_model=HealthResponse, summary="Health check with dependency status")
async def health_check() -> HealthResponse:
    """
    Returns overall status plus reachability of critical dependencies.
    """
    rules_status = "disabled"
    rules_detail = None
    extraction_status = "disabled"
    extraction_detail = None

    # Rust rules engine
    if settings.RULES_ENGINE_ENABLED:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(
                    f"{settings.RULES_ENGINE_URL.rstrip('/')}/health"
                )
                if resp.status_code == 200:
                    rules_status = "ok"
                    rules_detail = resp.json()
                else:
                    rules_status = "unreachable"
                    rules_detail = {
                        "status_code": resp.status_code,
                        "body": resp.text[:300],
                    }
        except Exception as e:
            rules_status = "unreachable"
            rules_detail = str(e)

    # Member 2 extraction + XGBoost service
    if settings.EXTRACTION_SERVICE_ENABLED:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(
                    f"{settings.EXTRACTION_SERVICE_URL.rstrip('/')}/health"
                )
                if resp.status_code == 200:
                    extraction_status = "ok"
                    extraction_detail = resp.json()
                else:
                    extraction_status = "unreachable"
                    extraction_detail = {
                        "status_code": resp.status_code,
                        "body": resp.text[:300],
                    }
        except Exception as e:
            extraction_status = "unreachable"
            extraction_detail = str(e)

    # Overall status
    overall = "ok"
    if rules_status == "unreachable" or extraction_status == "unreachable":
        overall = "degraded"

    return HealthResponse(
        status=overall,
        service="medical-bill-backend",
        version=APP_VERSION,
        environment=settings.ENVIRONMENT,
        dependencies={
            "rules_engine": {
                "status": rules_status,
                "url": settings.RULES_ENGINE_URL,
                "enabled": settings.RULES_ENGINE_ENABLED,
                "detail": rules_detail,
            },
            "extraction_service": {
                "status": extraction_status,
                "url": settings.EXTRACTION_SERVICE_URL,
                "enabled": settings.EXTRACTION_SERVICE_ENABLED,
                "detail": extraction_detail,
            },
            "llm": {
                "enabled": settings.LLM_ENABLED,
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
            },
        },
    )