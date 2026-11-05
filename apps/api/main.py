"""
AndhaKaanun API — Main Application Entry Point

Production-grade FastAPI application with:
- Async lifespan management for service connections
- CORS middleware
- Structured JSON logging
- Router registration
- Exception handlers
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.config import get_settings
from apps.api.models.schemas import ErrorCode, ErrorDetail, ErrorResponse
from apps.api.routers import analyze, cases, system

# ──────────────────────────────────────────────
# Logging Setup
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("andhakaanun")


# ──────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ──────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage service connections:
      Startup  → connect Redis, Pinecone, DB pool
      Shutdown → close connections gracefully
    """
    settings = get_settings()
    logger.info(
        "Starting AndhaKaanun API v%s [env=%s]",
        settings.app_version,
        settings.environment,
    )

    # Record startup time for uptime tracking
    system.set_startup_time()

    # --- Redis connection ---
    try:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await redis_client.ping()
        app.state.redis = redis_client
        logger.info("✓ Redis connected: %s", settings.redis_url)
    except Exception as e:
        logger.warning("✗ Redis unavailable: %s (caching disabled)", e)
        app.state.redis = None

    # --- Pinecone connection ---
    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=settings.pinecone_api_key)
        app.state.pinecone_index = pc.Index(settings.pinecone_index)
        logger.info("✓ Pinecone connected: index=%s", settings.pinecone_index)
    except Exception as e:
        logger.warning("✗ Pinecone unavailable: %s (RAG disabled)", e)
        app.state.pinecone_index = None

    # --- PostgreSQL connection test ---
    try:
        from sqlalchemy import text

        from apps.api.db.base import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        app.state.db_engine = engine
        logger.info("✓ PostgreSQL connected")
    except Exception as e:
        logger.warning("✗ PostgreSQL unavailable: %s", e)
        app.state.db_engine = None

    logger.info("AndhaKaanun API ready — all services initialized.")

    yield  # ← Application runs here

    # --- Shutdown ---
    logger.info("Shutting down AndhaKaanun API...")

    if getattr(app.state, "db_engine", None):
        await app.state.db_engine.dispose()
        logger.info("✓ PostgreSQL pool disposed")

    if getattr(app.state, "redis", None):
        await app.state.redis.close()
        logger.info("✓ Redis disconnected")

    logger.info("Shutdown complete.")


# ──────────────────────────────────────────────
# Application Factory
# ──────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "AI-powered legal analysis engine for Indian law. "
            "Provides structured case analysis with prosecution/defense perspectives, "
            "applicable laws via RAG, and confidence scoring."
        ),
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request logging middleware ────────────
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = int((time.perf_counter() - start) * 1000)

        logger.info(
            "%s %s → %d (%dms)",
            request.method,
            request.url.path,
            response.status_code,
            latency_ms,
        )
        response.headers["X-Response-Time-Ms"] = str(latency_ms)
        return response

    # ── Exception Handlers ───────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """Transform Pydantic validation errors into our error schema."""
        errors = exc.errors()
        messages = [
            f"{err.get('loc', ['unknown'])[-1]}: {err.get('msg', 'Invalid')}" for err in errors
        ]
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                detail=ErrorDetail(
                    error=ErrorCode.INSUFFICIENT_CONTEXT,
                    message="; ".join(messages),
                    suggestions=[
                        "Provide at least 50 characters of case description",
                        "Include relevant details about the incident",
                    ],
                    min_length=50,
                )
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def global_error_handler(request: Request, exc: Exception):
        """Catch-all for unhandled exceptions."""
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                detail=ErrorDetail(
                    error=ErrorCode.INTERNAL_ERROR,
                    message="An unexpected error occurred. Please try again.",
                    suggestions=["If the issue persists, contact support."],
                )
            ).model_dump(),
        )

    # ── Routers ──────────────────────────────
    app.include_router(system.router)
    app.include_router(analyze.router)
    app.include_router(cases.router)

    return app


# ──────────────────────────────────────────────
# Application Instance
# ──────────────────────────────────────────────

app = create_app()


# ──────────────────────────────────────────────
# Dev Server
# ──────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "apps.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
