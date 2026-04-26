"""
SQLAlchemy ORM models — matches PRD Section 3.1 PostgreSQL schema exactly.

Tables:
  - cases          : Input cases with jurisdiction metadata
  - analysis       : 1:1 with cases — full LLM analysis output
  - request_logs   : Per-request latency, token, and error tracking
  - feedback       : User thumbs-up/down per analysis
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.db.base import Base


# ──────────────────────────────────────────────
# Cases
# ──────────────────────────────────────────────

class Case(Base):
    """Input case with jurisdiction metadata."""

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    jurisdiction: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, comment="{country, state, domain}"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    ip_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="SHA-256 of client IP for rate limiting, no PII"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    analysis: Mapped[Optional["Analysis"]] = relationship(
        back_populates="case",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    request_logs: Mapped[list["RequestLog"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    __table_args__ = (
        Index("idx_cases_created", "created_at", postgresql_using="btree"),
    )

    def __repr__(self) -> str:
        return f"<Case id={self.id} status={self.status}>"


# ──────────────────────────────────────────────
# Analysis (1:1 with cases)
# ──────────────────────────────────────────────

class Analysis(Base):
    """Full LLM analysis output stored for retrieval and auditing."""

    __tablename__ = "analysis"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timeline: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    laws: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment="[{section, title, explanation, similarity_score}]",
    )
    prosecution: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    defense: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    consequences: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    missing_info: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True
    )
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    raw_llm_output: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Full LLM response for debugging/auditing"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    case: Mapped["Case"] = relationship(back_populates="analysis")

    __table_args__ = (
        Index("idx_analysis_case", "case_id", postgresql_using="btree"),
    )

    def __repr__(self) -> str:
        return f"<Analysis id={self.id} case_id={self.case_id} confidence={self.confidence_score}>"


# ──────────────────────────────────────────────
# Request Logs
# ──────────────────────────────────────────────

class RequestLog(Base):
    """Per-request performance and error tracking."""

    __tablename__ = "request_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
    )
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rag_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    llm_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    case: Mapped[Optional["Case"]] = relationship(back_populates="request_logs")

    __table_args__ = (
        Index("idx_logs_case", "case_id", postgresql_using="btree"),
    )

    def __repr__(self) -> str:
        return f"<RequestLog id={self.id} latency={self.latency_ms}ms>"


# ──────────────────────────────────────────────
# Feedback
# ──────────────────────────────────────────────

class Feedback(Base):
    """User feedback on analysis quality."""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    case: Mapped["Case"] = relationship(back_populates="feedbacks")

    def __repr__(self) -> str:
        return f"<Feedback id={self.id} helpful={self.helpful}>"
