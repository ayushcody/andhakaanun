"""
GET /cases — Case retrieval and listing endpoints.
Wired to database with full persistence.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from apps.api.config import Settings
from apps.api.dependencies import get_current_settings
from apps.api.models.schemas import (
    AnalysisResponse,
    CaseListItem,
    CaseListResponse,
    CaseResponse,
    CaseStatus,
    ConsequencesDetail,
    DefenseDetail,
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    JurisdictionInfo,
    LawDetail,
    ProsecutionDetail,
)

logger = logging.getLogger("andhakaanun.api.cases")

MOCK_DB: dict[str, CaseResponse] = {}

router = APIRouter(prefix="/cases", tags=["Cases"])


def _db_case_to_response(case) -> CaseResponse:
    """Convert a DB Case model instance to Pydantic response."""
    analysis_response = None

    if case.analysis:
        a = case.analysis

        laws = []
        for law in a.laws or []:
            laws.append(
                LawDetail(
                    section=law.get("section", ""),
                    title=law.get("title", ""),
                    explanation=law.get("explanation", ""),
                    applies_because=law.get("applies_because", ""),
                    similarity_score=float(law.get("similarity_score", 0.5)),
                )
            )

        prosecution_data = a.prosecution or {}
        defense_data = a.defense or {}

        # Handle consequences — stored as text or dict
        consequences_data = {}
        if a.consequences:
            if isinstance(a.consequences, dict):
                consequences_data = a.consequences
            elif isinstance(a.consequences, str):
                try:
                    consequences_data = json.loads(a.consequences)
                except (json.JSONDecodeError, TypeError):
                    consequences_data = {"criminal": a.consequences, "civil": "", "bail_status": ""}

        analysis_response = AnalysisResponse(
            case_id=case.id,
            summary=a.summary or "",
            timeline=a.timeline or [],
            laws=laws,
            prosecution=ProsecutionDetail(
                main_argument=prosecution_data.get("main_argument", ""),
                strongest_points=prosecution_data.get("strongest_points", []),
                burden_of_proof=prosecution_data.get("burden_of_proof", ""),
            ),
            defense=DefenseDetail(
                main_argument=defense_data.get("main_argument", ""),
                counter_points=defense_data.get("counter_points", []),
                possible_loopholes=defense_data.get("possible_loopholes", []),
            ),
            consequences=ConsequencesDetail(
                criminal=consequences_data.get("criminal", ""),
                civil=consequences_data.get("civil", ""),
                bail_status=consequences_data.get("bail_status", ""),
            ),
            confidence_score=float(a.confidence_score) if a.confidence_score else 0.0,
            missing_info=list(a.missing_info) if a.missing_info else [],
        )

    jurisdiction = None
    if case.jurisdiction:
        jurisdiction = JurisdictionInfo(
            country=case.jurisdiction.get("country", "India"),
            state=case.jurisdiction.get("state"),
            domain=case.jurisdiction.get("domain", []),
        )

    return CaseResponse(
        id=case.id,
        input_text=case.input_text,
        location=case.location,
        jurisdiction=jurisdiction,
        status=CaseStatus(case.status),
        created_at=case.created_at,
        analysis=analysis_response,
    )


@router.get(
    "/{case_id}",
    response_model=CaseResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Case not found"},
    },
    summary="Retrieve a saved case analysis",
)
async def get_case(
    case_id: UUID,
    request: Request,
    settings: Settings = Depends(get_current_settings),
):
    """Retrieve a previously analyzed case by its UUID."""
    db_engine = getattr(request.app.state, "db_engine", None)
    if not db_engine:
        if str(case_id) in MOCK_DB:
            return MOCK_DB[str(case_id)]
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                detail=ErrorDetail(
                    error=ErrorCode.INTERNAL_ERROR,
                    message="Database not available, and case not found in mock cache.",
                    suggestions=["Database connection is not configured. Try again later."],
                )
            ).model_dump(),
        )

    try:
        from apps.api.db.base import async_session_factory
        from apps.api.db.crud import get_case_by_id

        async with async_session_factory() as session:
            case = await get_case_by_id(session, case_id, load_analysis=True)
            if not case:
                return JSONResponse(
                    status_code=404,
                    content=ErrorResponse(
                        detail=ErrorDetail(
                            error=ErrorCode.INTERNAL_ERROR,
                            message=f"Case {case_id} not found.",
                            suggestions=["Check the case ID and try again."],
                        )
                    ).model_dump(),
                )

            return _db_case_to_response(case)

    except Exception:
        logger.exception("Failed to retrieve case %s", case_id)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                detail=ErrorDetail(
                    error=ErrorCode.INTERNAL_ERROR,
                    message="Failed to retrieve case.",
                    suggestions=["Try again later."],
                )
            ).model_dump(),
        )


@router.get(
    "",
    response_model=CaseListResponse,
    summary="List analyzed cases (paginated)",
)
async def list_cases_endpoint(
    request: Request,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    settings: Settings = Depends(get_current_settings),
):
    """List cases with pagination, ordered by creation date descending."""
    db_engine = getattr(request.app.state, "db_engine", None)
    if not db_engine:
        return CaseListResponse(cases=[], total=0, page=page, page_size=page_size, has_next=False)

    try:
        from apps.api.db.base import async_session_factory
        from apps.api.db.crud import list_cases

        async with async_session_factory() as session:
            cases, total = await list_cases(session, page=page, page_size=page_size)

            items = []
            for case in cases:
                confidence = None
                summary_preview = case.input_text[:200]
                if case.analysis:
                    confidence = (
                        float(case.analysis.confidence_score)
                        if case.analysis.confidence_score
                        else None
                    )
                    if case.analysis.summary:
                        summary_preview = case.analysis.summary[:200]

                items.append(
                    CaseListItem(
                        id=case.id,
                        summary_preview=summary_preview,
                        status=CaseStatus(case.status),
                        confidence_score=confidence,
                        created_at=case.created_at,
                    )
                )

            return CaseListResponse(
                cases=items,
                total=total,
                page=page,
                page_size=page_size,
                has_next=(page * page_size < total),
            )

    except Exception:
        logger.exception("Failed to list cases")
        return CaseListResponse(cases=[], total=0, page=page, page_size=page_size, has_next=False)
