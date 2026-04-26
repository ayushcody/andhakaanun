"""
POST /analyze-case — Core analysis endpoint.
Supports both streaming (SSE) and non-streaming responses.

Wires together: Jurisdiction → RAG Retrieval → LLM Reasoning → DB Persistence
Matches PRD §6.1 fully.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from apps.api.config import Settings
from apps.api.dependencies import get_current_settings, get_db_session
from apps.api.models.schemas import (
    AnalysisResponse,
    CaseRequest,
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    LawDetail,
    ProsecutionDetail,
    DefenseDetail,
    ConsequencesDetail,
    RefineRequest,
)
from apps.api.services.cache import CacheService
from apps.api.services.jurisdiction import detect_jurisdiction
from apps.api.services.reasoning import run_reasoning
from apps.api.services.retrieval import retrieve_laws

logger = logging.getLogger("andhakaanun.api.analyze")

router = APIRouter(tags=["Analysis"])


def _hash_ip(ip: str) -> str:
    """SHA-256 hash of client IP for rate limiting — no PII stored."""
    return hashlib.sha256(ip.encode()).hexdigest()


def _build_analysis_response(
    case_id: uuid.UUID,
    analysis: dict[str, Any],
    from_cache: bool = False,
) -> AnalysisResponse:
    """Convert raw analysis dict to validated Pydantic response."""
    laws = []
    for law in analysis.get("laws", []):
        laws.append(
            LawDetail(
                section=law.get("section", "Unknown"),
                title=law.get("title", ""),
                explanation=law.get("explanation", ""),
                applies_because=law.get("applies_because", ""),
                similarity_score=min(max(float(law.get("similarity_score", 0.5)), 0.0), 1.0),
            )
        )

    prosecution = analysis.get("prosecution", {})
    defense = analysis.get("defense", {})
    consequences = analysis.get("consequences", {})

    return AnalysisResponse(
        case_id=case_id,
        summary=analysis.get("summary", "Analysis unavailable."),
        timeline=analysis.get("timeline", []),
        laws=laws,
        prosecution=ProsecutionDetail(
            main_argument=prosecution.get("main_argument", "Not determined"),
            strongest_points=prosecution.get("strongest_points", []),
            burden_of_proof=prosecution.get("burden_of_proof", "Not determined"),
        ),
        defense=DefenseDetail(
            main_argument=defense.get("main_argument", "Not determined"),
            counter_points=defense.get("counter_points", []),
            possible_loopholes=defense.get("possible_loopholes", []),
        ),
        consequences=ConsequencesDetail(
            criminal=consequences.get("criminal", "Not determined"),
            civil=consequences.get("civil", "Not determined"),
            bail_status=consequences.get("bail_status", "Not determined"),
        ),
        confidence_score=min(max(float(analysis.get("confidence_score", 0.3)), 0.0), 1.0),
        missing_info=analysis.get("missing_info", []),
        from_cache=from_cache,
        disclaimer=analysis.get(
            "disclaimer",
            "This analysis is AI-generated and not legal advice. Consult a qualified lawyer.",
        ),
    )


async def _run_pipeline(
    body: CaseRequest,
    request: Request,
    settings: Settings,
) -> dict[str, Any]:
    """
    Full analysis pipeline:
      1. Cache check
      2. Jurisdiction detection
      3. RAG retrieval
      4. LLM reasoning
      5. Cache set
      6. DB persistence
      7. Request logging

    Returns dict with: case_id, analysis, metadata, from_cache
    """
    start_time = time.perf_counter()
    case_id = uuid.uuid4()
    ip_hash = _hash_ip(request.client.host if request.client else "unknown")

    redis_client = getattr(request.app.state, "redis", None)
    pinecone_index = getattr(request.app.state, "pinecone_index", None)

    metadata: dict[str, Any] = {
        "case_id": str(case_id),
        "rag_latency_ms": 0,
        "llm_latency_ms": 0,
        "total_latency_ms": 0,
        "token_count": 0,
        "model_version": None,
        "from_cache": False,
    }

    # ── 1. Cache check ──────────────────────
    cache = CacheService(redis_client, ttl_seconds=settings.cache_ttl_seconds)
    cached = await cache.get(body.case_text, body.location)
    if cached:
        metadata["from_cache"] = True
        metadata["total_latency_ms"] = int((time.perf_counter() - start_time) * 1000)
        logger.info("Cache HIT — returning cached analysis in %dms", metadata["total_latency_ms"])
        return {
            "case_id": case_id,
            "analysis": cached,
            "metadata": metadata,
            "from_cache": True,
        }

    # ── 2. Jurisdiction detection ───────────
    jurisdiction = await detect_jurisdiction(body.case_text, body.location)

    # ── 3. RAG retrieval ────────────────────
    rag_start = time.perf_counter()
    retrieved, rag_meta = await retrieve_laws(
        query=body.case_text,
        domains=jurisdiction.detected_domains or None,
        top_k=5,
        pinecone_index=pinecone_index,
        redis_client=redis_client,
        pinecone_timeout=settings.pinecone_timeout_seconds,
    )
    metadata["rag_latency_ms"] = int((time.perf_counter() - rag_start) * 1000)

    # ── 4. LLM reasoning ───────────────────
    llm_start = time.perf_counter()
    from apps.api.services.llm_client import LLMClient
    llm_client = LLMClient()
    if body.groq_api_key:
        llm_client.set_api_key(body.groq_api_key)

    reasoning_result = await run_reasoning(
        case_text=body.case_text,
        location=body.location,
        domains=jurisdiction.detected_domains,
        retrieved_laws=retrieved,
        llm_client=llm_client,
    )
    metadata["llm_latency_ms"] = int((time.perf_counter() - llm_start) * 1000)

    analysis = reasoning_result["analysis"]
    reasoning_meta = reasoning_result["metadata"]
    metadata["token_count"] = reasoning_meta.get("token_count", 0)
    metadata["model_version"] = reasoning_meta.get("model")

    # ── 5. Cache set ────────────────────────
    await cache.set(body.case_text, body.location, analysis)

    # ── 6. DB persistence ───────────────────
    db_engine = getattr(request.app.state, "db_engine", None)
    if db_engine:
        try:
            from apps.api.db.base import async_session_factory
            from apps.api.db.crud import create_analysis, create_case, create_request_log, update_case_status

            async with async_session_factory() as session:
                # Create case
                case = await create_case(
                    session,
                    input_text=body.case_text,
                    location=body.location,
                    jurisdiction={
                        "country": "India",
                        "state": body.location,
                        "domain": jurisdiction.detected_domains,
                    },
                    ip_hash=ip_hash,
                    status="completed",
                )
                case_id = case.id

                # Create analysis
                await create_analysis(
                    session,
                    case_id=case_id,
                    summary=analysis.get("summary"),
                    timeline=analysis.get("timeline"),
                    laws=analysis.get("laws"),
                    prosecution=analysis.get("prosecution"),
                    defense=analysis.get("defense"),
                    consequences=json.dumps(analysis.get("consequences", {})),
                    missing_info=analysis.get("missing_info"),
                    confidence_score=analysis.get("confidence_score"),
                    raw_llm_output=reasoning_meta.get("raw_text", json.dumps(analysis)),
                )

                # Log request
                metadata["total_latency_ms"] = int((time.perf_counter() - start_time) * 1000)
                await create_request_log(
                    session,
                    case_id=case_id,
                    latency_ms=metadata["total_latency_ms"],
                    rag_latency_ms=metadata["rag_latency_ms"],
                    llm_latency_ms=metadata["llm_latency_ms"],
                    token_count=metadata["token_count"],
                    model_version=metadata["model_version"],
                )

                await session.commit()
                logger.info("✓ Persisted case %s to database", case_id)

        except Exception as e:
            logger.warning("DB persistence failed (non-blocking): %s", e)
    else:
        from datetime import datetime
        from apps.api.routers.cases import MOCK_DB
        from apps.api.models.schemas import CaseResponse, CaseStatus, JurisdictionInfo
        response_mock = _build_analysis_response(case_id=case_id, analysis=analysis, from_cache=False)
        MOCK_DB[str(case_id)] = CaseResponse(
            id=case_id,
            input_text=body.case_text,
            location=body.location,
            jurisdiction=JurisdictionInfo(country="India", state=body.location, domain=jurisdiction.detected_domains),
            status=CaseStatus.COMPLETED,
            created_at=datetime.utcnow(),
            analysis=response_mock
        )

    metadata["total_latency_ms"] = int((time.perf_counter() - start_time) * 1000)
    metadata["case_id"] = str(case_id)

    logger.info(
        json.dumps({
            "event": "analysis_complete",
            "case_id": str(case_id),
            "rag_ms": metadata["rag_latency_ms"],
            "llm_ms": metadata["llm_latency_ms"],
            "total_ms": metadata["total_latency_ms"],
            "confidence": analysis.get("confidence_score"),
            "laws_retrieved": len(retrieved),
            "from_cache": False,
        })
    )

    return {
        "case_id": case_id,
        "analysis": analysis,
        "metadata": metadata,
        "from_cache": False,
    }


# ──────────────────────────────────────────────
# SSE Streaming Generator (PRD §6.1)
# ──────────────────────────────────────────────

async def _stream_analysis(
    body: CaseRequest,
    request: Request,
    settings: Settings,
) -> AsyncGenerator[dict, None]:
    """
    Stream analysis as Server-Sent Events.
    Events: summary → laws → perspectives → complete
    """
    try:
        result = await _run_pipeline(body, request, settings)
        analysis = result["analysis"]
        case_id = str(result["case_id"])

        # Event 1: Summary
        yield {
            "event": "summary",
            "data": json.dumps({
                "case_id": case_id,
                "summary": analysis.get("summary", ""),
                "timeline": analysis.get("timeline", []),
            }),
        }
        await asyncio.sleep(0.05)

        # Event 2: Laws
        yield {
            "event": "laws",
            "data": json.dumps({
                "laws": analysis.get("laws", []),
            }),
        }
        await asyncio.sleep(0.05)

        # Event 3: Perspectives
        yield {
            "event": "perspectives",
            "data": json.dumps({
                "prosecution": analysis.get("prosecution", {}),
                "defense": analysis.get("defense", {}),
            }),
        }
        await asyncio.sleep(0.05)

        # Event 4: Complete
        yield {
            "event": "complete",
            "data": json.dumps({
                "case_id": case_id,
                "consequences": analysis.get("consequences", {}),
                "confidence_score": analysis.get("confidence_score", 0.3),
                "missing_info": analysis.get("missing_info", []),
                "from_cache": result.get("from_cache", False),
                "disclaimer": analysis.get("disclaimer", ""),
            }),
        }

    except Exception as e:
        logger.exception("Streaming analysis failed")
        yield {
            "event": "error",
            "data": json.dumps({
                "error": "INTERNAL_ERROR",
                "message": str(e),
            }),
        }


# ──────────────────────────────────────────────
# Route Handler
# ──────────────────────────────────────────────

@router.post(
    "/analyze-case",
    response_model=AnalysisResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
        429: {"model": ErrorResponse, "description": "Rate limited"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
    summary="Analyze a legal case",
    description=(
        "Accepts a case narrative and location, runs jurisdiction detection, "
        "RAG retrieval, and LLM reasoning to produce a structured legal analysis."
    ),
)
async def analyze_case(
    body: CaseRequest,
    request: Request,
    settings: Settings = Depends(get_current_settings),
):
    """
    Full analysis pipeline:
    1. Jurisdiction detection
    2. RAG retrieval from Pinecone
    3. LLM reasoning via Groq
    4. Structured response

    Supports streaming (SSE) via ?stream=true or body.stream=true.
    """
    # --- Streaming mode ---
    if body.stream:
        return EventSourceResponse(
            _stream_analysis(body, request, settings),
            media_type="text/event-stream",
        )

    # --- Non-streaming mode ---
    try:
        result = await _run_pipeline(body, request, settings)
        response = _build_analysis_response(
            case_id=result["case_id"],
            analysis=result["analysis"],
            from_cache=result.get("from_cache", False),
        )
        return response

    except TimeoutError:
        return JSONResponse(
            status_code=504,
            content=ErrorResponse(
                detail=ErrorDetail(
                    error=ErrorCode.LLM_TIMEOUT,
                    message="Analysis timed out. The AI model took too long to respond.",
                    suggestions=[
                        "Try again in a few seconds",
                        "Try with a shorter case description",
                    ],
                )
            ).model_dump(),
        )

    except Exception as e:
        logger.exception("Analysis failed: %s", e)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                detail=ErrorDetail(
                    error=ErrorCode.INTERNAL_ERROR,
                    message="An unexpected error occurred during analysis.",
                    suggestions=["Please try again. If the issue persists, contact support."],
                )
            ).model_dump(),
        )


# ──────────────────────────────────────────────
# Interactive Refinement
# ──────────────────────────────────────────────

@router.post(
    "/cases/{case_id}/refine",
    response_model=AnalysisResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
        404: {"model": ErrorResponse, "description": "Case not found"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
    summary="Refine analysis with follow-up answers",
    description="Appends follow-up answers to the case text and reruns the full pipeline.",
)
async def refine_case(
    case_id: uuid.UUID,
    body: RefineRequest,
    request: Request,
    settings: Settings = Depends(get_current_settings),
):
    """
    1. Fetch existing case
    2. Append Q&A to case text
    3. Re-run RAG + LLM Reasoning
    4. Update DB (overwrite analysis to reflect refined version)
    """
    db_engine = getattr(request.app.state, "db_engine", None)
    try:
        from apps.api.db.base import async_session_factory
        from apps.api.db.crud import get_case_by_id, update_analysis
        from apps.api.routers.cases import MOCK_DB

        if not db_engine:
            mock_case = MOCK_DB.get(str(case_id))
            if not mock_case:
                return JSONResponse(status_code=404, content=ErrorResponse(
                    detail=ErrorDetail(error=ErrorCode.INTERNAL_ERROR, message=f"Case {case_id} not found.")).model_dump())
            case_location = mock_case.location
            new_text = mock_case.input_text
        else:
            async with async_session_factory() as session:
                case = await get_case_by_id(session, case_id, load_analysis=False)
                if not case:
                    return JSONResponse(status_code=404, content=ErrorResponse(
                        detail=ErrorDetail(error=ErrorCode.INTERNAL_ERROR, message=f"Case {case_id} not found.")).model_dump())
                case_location = case.location
                new_text = case.input_text

        # Append Q&A to case text
        new_text += "\n\nFollow-up Context provided by the user:"
        for answer in body.answers:
            new_text += f"\n- Q: {answer.question}\n- A: {answer.answer}"

        if db_engine:
            async with async_session_factory() as session:
                case = await get_case_by_id(session, case_id, load_analysis=False)
                case.input_text = new_text
                await session.commit()
        else:
            mock_case = MOCK_DB.get(str(case_id))
            if mock_case:
                mock_case.input_text = new_text

        # Create mock CaseRequest to reuse jurisdiction & RAG
        # For simplicity, we just run the services directly
        start_time = time.perf_counter()
        jurisdiction = await detect_jurisdiction(new_text, case_location or "")

        redis_client = getattr(request.app.state, "redis", None)
        pinecone_index = getattr(request.app.state, "pinecone_index", None)

        retrieved, rag_meta = await retrieve_laws(
            query=new_text,
            domains=jurisdiction.detected_domains or None,
            top_k=5,
            pinecone_index=pinecone_index,
            redis_client=redis_client,
            pinecone_timeout=settings.pinecone_timeout_seconds,
        )

        from apps.api.services.llm_client import LLMClient
        llm_client = LLMClient()
        if body.groq_api_key:
            llm_client.set_api_key(body.groq_api_key)

        reasoning_result = await run_reasoning(
            case_text=new_text,
            location=case_location or "India",
            domains=jurisdiction.detected_domains,
            retrieved_laws=retrieved,
            llm_client=llm_client,
        )

        analysis = reasoning_result["analysis"]
        reasoning_meta = reasoning_result["metadata"]

        if db_engine:
            async with async_session_factory() as session:
                await update_analysis(
                    session,
                    case_id=case_id,
                    summary=analysis.get("summary"),
                    timeline=analysis.get("timeline"),
                    laws=analysis.get("laws"),
                    prosecution=analysis.get("prosecution"),
                    defense=analysis.get("defense"),
                    consequences=json.dumps(analysis.get("consequences", {})),
                    missing_info=analysis.get("missing_info"),
                    confidence_score=analysis.get("confidence_score"),
                    raw_llm_output=reasoning_meta.get("raw_text", json.dumps(analysis)),
                )
                await session.commit()
            logger.info("✓ Refined case %s in database", case_id)

        response = _build_analysis_response(
            case_id=case_id,
            analysis=analysis,
            from_cache=False,
        )

        if not db_engine:
            mock_case = MOCK_DB.get(str(case_id))
            if mock_case:
                mock_case.analysis = response

        return response

    except Exception as e:
        logger.exception("Refinement failed: %s", e)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                detail=ErrorDetail(
                    error=ErrorCode.INTERNAL_ERROR,
                    message="An unexpected error occurred during refinement.",
                    suggestions=["Please try again."],
                )
            ).model_dump(),
        )


# ──────────────────────────────────────────────
# Quick Jurisdiction Detect (for live badges)
# ──────────────────────────────────────────────

@router.post(
    "/detect-jurisdiction",
    summary="Quick jurisdiction detection for real-time UI",
    description="Fast keyword-based detection — returns matched sections as badges.",
)
async def detect_jurisdiction_endpoint(
    body: dict,
):
    """Returns jurisdiction badges as user types (PRD §7.1 micro-interaction)."""
    from apps.api.services.jurisdiction import quick_detect

    text = body.get("text", "")
    if len(text) < 10:
        return {"badges": []}

    badges = quick_detect(text)
    return {"badges": badges}
