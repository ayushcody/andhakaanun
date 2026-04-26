"""
GET /health — Service health check.
POST /feedback — User feedback on analysis quality.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from apps.api.config import Settings
from apps.api.dependencies import get_current_settings
from apps.api.models.schemas import (
    FeedbackRequest,
    HealthResponse,
    ServiceHealth,
)

router = APIRouter(tags=["System"])

# Track startup time for uptime calculation
_startup_time: float = time.time()


def set_startup_time() -> None:
    """Called from lifespan to record accurate startup timestamp."""
    global _startup_time
    _startup_time = time.time()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description="Returns health status of all downstream services.",
)
async def health_check(
    request: Request,
    settings: Settings = Depends(get_current_settings),
) -> HealthResponse:
    """
    Checks connectivity to:
    - PostgreSQL (via session ping)
    - Redis (via PING command)
    - Pinecone (via describe_index_stats)
    """
    services: dict[str, ServiceHealth] = {}
    overall_status = "healthy"

    # --- PostgreSQL ---
    db_engine = getattr(request.app.state, "db_engine", None)
    if db_engine:
        try:
            from sqlalchemy import text

            start = time.perf_counter()
            async with db_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            latency = int((time.perf_counter() - start) * 1000)
            services["postgresql"] = ServiceHealth(status="ok", latency_ms=latency)
        except Exception as e:
            services["postgresql"] = ServiceHealth(
                status="down", message=str(e)
            )
            overall_status = "degraded"
    else:
        services["postgresql"] = ServiceHealth(
            status="down", message="Not initialized"
        )

    # --- Redis ---
    redis = getattr(request.app.state, "redis", None)
    if redis:
        try:
            start = time.perf_counter()
            await redis.ping()
            latency = int((time.perf_counter() - start) * 1000)
            services["redis"] = ServiceHealth(status="ok", latency_ms=latency)
        except Exception as e:
            services["redis"] = ServiceHealth(
                status="down", message=str(e)
            )
            overall_status = "degraded"
    else:
        services["redis"] = ServiceHealth(
            status="down", message="Not initialized"
        )

    # --- Pinecone ---
    pinecone_index = getattr(request.app.state, "pinecone_index", None)
    if pinecone_index:
        try:
            start = time.perf_counter()
            pinecone_index.describe_index_stats()
            latency = int((time.perf_counter() - start) * 1000)
            services["pinecone"] = ServiceHealth(status="ok", latency_ms=latency)
        except Exception as e:
            services["pinecone"] = ServiceHealth(
                status="down", message=str(e)
            )
            overall_status = "degraded"
    else:
        services["pinecone"] = ServiceHealth(
            status="down", message="Not initialized"
        )

    if any(s.status == "down" for s in services.values()):
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        services=services,
        uptime_seconds=round(time.time() - _startup_time, 2),
    )


@router.post(
    "/feedback",
    status_code=202,
    summary="Submit feedback on an analysis",
    description="Thumbs up/down feedback for quality monitoring.",
)
async def submit_feedback(
    body: FeedbackRequest,
    request: Request,
    settings: Settings = Depends(get_current_settings),
):
    """
    Store user feedback. Persisted to database if available.
    Returns 202 Accepted immediately.
    """
    db_engine = getattr(request.app.state, "db_engine", None)
    if db_engine:
        try:
            from apps.api.db.base import async_session_factory
            from apps.api.db.crud import create_feedback

            async with async_session_factory() as session:
                await create_feedback(
                    session,
                    case_id=body.case_id,
                    helpful=body.helpful,
                    comment=body.comment,
                )
                await session.commit()
        except Exception:
            pass  # Best-effort — don't fail the feedback endpoint

    return {"status": "accepted", "case_id": str(body.case_id)}
