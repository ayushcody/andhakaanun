"""
Dependency injection container for FastAPI.
Provides database sessions, service instances, and settings.
"""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends, Request

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import Settings, get_settings
from apps.api.db.base import get_async_session


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an async database session with automatic commit/rollback.
    Uses the session factory from db.base.
    """
    async for session in get_async_session():
        yield session


async def get_redis_client(request: Request):
    """
    Retrieve Redis client from app state.
    Initialized in lifespan.
    """
    return getattr(request.app.state, "redis", None)


async def get_pinecone_index(request: Request):
    """
    Retrieve Pinecone index from app state.
    Initialized in lifespan.
    """
    return getattr(request.app.state, "pinecone_index", None)


def get_current_settings() -> Settings:
    """Dependency wrapper for settings — enables override in tests."""
    return get_settings()
