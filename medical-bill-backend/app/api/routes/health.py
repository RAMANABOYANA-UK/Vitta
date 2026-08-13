"""
Health check endpoint.

Reports overall service health plus the reachability of the Rust
rules engine, so operators can see at a glance whether deterministic
rule application is degraded.
"""
import httpx
from fastapi import APIRouter

from app.config import settings
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])

APP_VERSION = "0.2.0"


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health_check() -> HealthResponse:
    """Report overall health plus rules-engine reachability."""
    rules_status = "disabled"
    rules_detail = None

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
                        "body": resp.text[:500],
                    }
        except Exception as e:
            rules_status = "unreachable"
            rules_detail = str(e)

    # Overall is "ok" unless the rules engine is required but unreachable.
    overall = "ok" if rules_status in ("ok", "disabled") else "degraded"

    return HealthResponse(
        status=overall,
        environment=settings.ENVIRONMENT,
        version=APP_VERSION,
        rules_engine={
            "status": rules_status,
            "url": settings.RULES_ENGINE_URL,
            "detail": rules_detail,
        },
        llm_enabled=settings.LLM_ENABLED,
    )