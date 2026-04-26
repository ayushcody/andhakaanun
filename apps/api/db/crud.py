"""
CRUD operations for all database models.
Thin async wrappers — no business logic here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.db.models import Analysis, Case, Feedback, RequestLog


# ──────────────────────────────────────────────
# Cases
# ──────────────────────────────────────────────

async def create_case(
    session: AsyncSession,
    *,
    input_text: str,
    location: str | None = None,
    jurisdiction: dict | None = None,
    ip_hash: str | None = None,
    status: str = "pending",
) -> Case:
    """Insert a new case record."""
    case = Case(
        input_text=input_text,
        location=location,
        jurisdiction=jurisdiction,
        ip_hash=ip_hash,
        status=status,
    )
    session.add(case)
    await session.flush()  # Populate id
    return case


async def get_case_by_id(
    session: AsyncSession,
    case_id: uuid.UUID,
    *,
    load_analysis: bool = True,
) -> Case | None:
    """Fetch a case by UUID, optionally with analysis eagerly loaded."""
    stmt = select(Case).where(Case.id == case_id)
    if load_analysis:
        stmt = stmt.options(selectinload(Case.analysis))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_case_status(
    session: AsyncSession,
    case_id: uuid.UUID,
    status: str,
) -> None:
    """Update case status (pending → processing → completed → failed)."""
    case = await session.get(Case, case_id)
    if case:
        case.status = status
        await session.flush()


async def list_cases(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[Case], int]:
    """
    Paginated case listing, ordered by created_at DESC.
    Returns (cases, total_count).
    """
    # Count
    count_stmt = select(func.count()).select_from(Case)
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    stmt = (
        select(Case)
        .options(selectinload(Case.analysis))
        .order_by(desc(Case.created_at))
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(stmt)
    cases = result.scalars().all()

    return cases, total


# ──────────────────────────────────────────────
# Analysis
# ──────────────────────────────────────────────

async def create_analysis(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    summary: str | None = None,
    timeline: list | None = None,
    laws: list | None = None,
    prosecution: dict | None = None,
    defense: dict | None = None,
    consequences: str | None = None,
    missing_info: list[str] | None = None,
    confidence_score: float | None = None,
    raw_llm_output: str | None = None,
) -> Analysis:
    """Insert an analysis record linked to a case."""
    analysis = Analysis(
        case_id=case_id,
        summary=summary,
        timeline=timeline,
        laws=laws,
        prosecution=prosecution,
        defense=defense,
        consequences=consequences,
        missing_info=missing_info,
        confidence_score=confidence_score,
        raw_llm_output=raw_llm_output,
    )
    session.add(analysis)
    await session.flush()
    return analysis


async def update_analysis(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    summary: str | None = None,
    timeline: list | None = None,
    laws: list | None = None,
    prosecution: dict | None = None,
    defense: dict | None = None,
    consequences: str | None = None,
    missing_info: list[str] | None = None,
    confidence_score: float | None = None,
    raw_llm_output: str | None = None,
) -> Analysis | None:
    """Update an existing analysis record."""
    analysis = await get_analysis_by_case_id(session, case_id)
    if not analysis:
        return None

    if summary is not None: analysis.summary = summary
    if timeline is not None: analysis.timeline = timeline
    if laws is not None: analysis.laws = laws
    if prosecution is not None: analysis.prosecution = prosecution
    if defense is not None: analysis.defense = defense
    if consequences is not None: analysis.consequences = consequences
    if missing_info is not None: analysis.missing_info = missing_info
    if confidence_score is not None: analysis.confidence_score = confidence_score
    if raw_llm_output is not None: analysis.raw_llm_output = raw_llm_output

    await session.flush()
    return analysis


async def get_analysis_by_case_id(
    session: AsyncSession,
    case_id: uuid.UUID,
) -> Analysis | None:
    """Fetch analysis for a specific case."""
    stmt = select(Analysis).where(Analysis.case_id == case_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ──────────────────────────────────────────────
# Request Logs
# ──────────────────────────────────────────────

async def create_request_log(
    session: AsyncSession,
    *,
    case_id: uuid.UUID | None = None,
    latency_ms: int | None = None,
    rag_latency_ms: int | None = None,
    llm_latency_ms: int | None = None,
    token_count: int | None = None,
    model_version: str | None = None,
    error: str | None = None,
) -> RequestLog:
    """Insert a request performance log."""
    log = RequestLog(
        case_id=case_id,
        latency_ms=latency_ms,
        rag_latency_ms=rag_latency_ms,
        llm_latency_ms=llm_latency_ms,
        token_count=token_count,
        model_version=model_version,
        error=error,
    )
    session.add(log)
    await session.flush()
    return log


# ──────────────────────────────────────────────
# Feedback
# ──────────────────────────────────────────────

async def create_feedback(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    helpful: bool,
    comment: str | None = None,
) -> Feedback:
    """Insert a feedback record."""
    fb = Feedback(
        case_id=case_id,
        helpful=helpful,
        comment=comment,
    )
    session.add(fb)
    await session.flush()
    return fb
