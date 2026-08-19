"""
Health check endpoint with full dependency visibility.

Reports overall service health plus the reachability of the Rust
rules engine and the Member 2 extraction/XGBoost service, so operators
can see at a glance whether any critical dependency is degraded.
"""
import httpx
from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])

APP_VERSION = "0.3.0"


async def _check_url(url: str, timeout: float = 2.0) -> str:
    """
    Quick reachability check for a dependency URL.
    Returns "ok" on 200, "unreachable" otherwise.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return "ok"
            return "unreachable"
    except Exception:
        return "unreachable"


@router.get("/health", summary="Health check with dependency status")
async def health_check() -> dict:
    """
    Returns overall status plus reachability of critical dependencies.
    """
    rules_status = "disabled"
    extraction_status = "disabled"

    if settings.RULES_ENGINE_ENABLED:
        rules_status = await _check_url(
            f"{settings.RULES_ENGINE_URL.rstrip('/')}/health",
        )
    if settings.EXTRACTION_SERVICE_ENABLED:
        extraction_status = await _check_url(
            f"{settings.EXTRACTION_SERVICE_URL.rstrip('/')}/health",
            timeout=settings.EXTRACTION_SERVICE_TIMEOUT_SECONDS,
        )

    overall = "ok"
    if settings.RULES_ENGINE_ENABLED and rules_status != "ok":
        overall = "degraded"
    if settings.EXTRACTION_SERVICE_ENABLED and extraction_status != "ok":
        overall = "degraded"

    return {
        "status": overall,
        "service": "medical-bill-backend",
        "environment": settings.ENVIRONMENT,
        "version": APP_VERSION,
        "rules_engine": {
            "enabled": settings.RULES_ENGINE_ENABLED,
            "status": rules_status,
            "url": settings.RULES_ENGINE_URL,
        },
        "extraction_service": {
            "enabled": settings.EXTRACTION_SERVICE_ENABLED,
            "status": extraction_status,
            "url": settings.EXTRACTION_SERVICE_URL,
        },
        "llm_enabled": settings.LLM_ENABLED,
        "auth_enabled": settings.AUTH_ENABLED,
    }
