"""
Pydantic v2 schemas for all API request/response contracts.
Matches PRD Section 6 — API Contract.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class CaseStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ErrorCode(str, Enum):
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    JURISDICTION_UNKNOWN = "JURISDICTION_UNKNOWN"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    RAG_FAILURE = "RAG_FAILURE"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class StreamEvent(str, Enum):
    SUMMARY = "summary"
    LAWS = "laws"
    PERSPECTIVES = "perspectives"
    COMPLETE = "complete"
    ERROR = "error"


# ──────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────

class CaseRequest(BaseModel):
    """POST /analyze-case request body."""
    case_text: str = Field(
        ...,
        min_length=50,
        max_length=3000,
        description="Detailed narrative of the legal case.",
        examples=["A car hit a pedestrian while speeding on MG Road, Pune..."],
    )
    location: str = Field(
        default="",
        max_length=100,
        description="Location/state where the incident occurred.",
        examples=["Pune", "Maharashtra"],
    )
    stream: bool = Field(
        default=False,
        description="If true, response is streamed via SSE.",
    )
    groq_api_key: Optional[str] = Field(
        default=None,
        description="Optional Groq API key from the frontend to bypass system settings.",
    )

    @field_validator("case_text")
    @classmethod
    def validate_case_text(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped.split()) < 10:
            raise ValueError(
                "Case description must contain at least 10 words for meaningful analysis."
            )
        return stripped


class FeedbackRequest(BaseModel):
    """POST /feedback request body."""
    case_id: UUID
    helpful: bool
    comment: Optional[str] = Field(default=None, max_length=500)


class RefineAnswer(BaseModel):
    """Single follow-up question and answer."""
    question: str
    answer: str


class RefineRequest(BaseModel):
    """POST /cases/{case_id}/refine request body."""
    answers: list[RefineAnswer]
    groq_api_key: Optional[str] = Field(
        default=None,
        description="Optional Groq API key from the frontend to bypass system settings.",
    )


# ──────────────────────────────────────────────
# Response Sub-Schemas
# ──────────────────────────────────────────────

class LawDetail(BaseModel):
    """Single applicable law entry."""
    section: str = Field(..., examples=["IPC 279"])
    title: str = Field(..., examples=["Rash driving on public way"])
    explanation: str
    applies_because: str
    similarity_score: float = Field(..., ge=0.0, le=1.0)


class ProsecutionDetail(BaseModel):
    """Prosecution perspective."""
    main_argument: str
    strongest_points: list[str]
    burden_of_proof: str


class DefenseDetail(BaseModel):
    """Defense perspective."""
    main_argument: str
    counter_points: list[str]
    possible_loopholes: list[str]


class ConsequencesDetail(BaseModel):
    """Potential legal consequences."""
    criminal: str
    civil: str
    bail_status: str


class JurisdictionInfo(BaseModel):
    """Detected jurisdiction metadata."""
    country: str = "India"
    state: Optional[str] = None
    domain: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────

class AnalysisResponse(BaseModel):
    """Full analysis result — used for non-streaming response."""
    case_id: UUID
    summary: str
    timeline: list[str]
    laws: list[LawDetail]
    prosecution: ProsecutionDetail
    defense: DefenseDetail
    consequences: ConsequencesDetail
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    missing_info: list[str]
    from_cache: bool = False
    disclaimer: str = (
        "This analysis is AI-generated and not legal advice. "
        "Consult a qualified lawyer."
    )


class CaseResponse(BaseModel):
    """GET /cases/:id response."""
    id: UUID
    input_text: str
    location: Optional[str]
    jurisdiction: Optional[JurisdictionInfo]
    status: CaseStatus
    created_at: datetime
    analysis: Optional[AnalysisResponse] = None


class CaseListItem(BaseModel):
    """Summary item for case listing."""
    id: UUID
    summary_preview: str = Field(..., max_length=200)
    status: CaseStatus
    confidence_score: Optional[float] = None
    created_at: datetime


class CaseListResponse(BaseModel):
    """GET /cases response (paginated)."""
    cases: list[CaseListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


# ──────────────────────────────────────────────
# Error Schemas
# ──────────────────────────────────────────────

class ErrorDetail(BaseModel):
    """Structured error response matching PRD Section 6.3."""
    error: ErrorCode
    message: str
    suggestions: list[str] = Field(default_factory=list)
    min_length: Optional[int] = None


class ErrorResponse(BaseModel):
    """Wrapper for error responses."""
    detail: ErrorDetail


# ──────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────

class ServiceHealth(BaseModel):
    """Individual service health status."""
    status: str  # "ok" | "degraded" | "down"
    latency_ms: Optional[int] = None
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """GET /health response."""
    status: str  # "healthy" | "degraded" | "unhealthy"
    version: str
    services: dict[str, ServiceHealth]
    uptime_seconds: float
