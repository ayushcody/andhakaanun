"""Initial schema — cases, analysis, request_logs, feedback

Revision ID: 001_initial
Revises: None
Create Date: 2026-04-14 UTC
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Cases ────────────────────────────────
    op.create_table(
        "cases",
        sa.Column(
            "id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True
        ),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("location", sa.String(100), nullable=True),
        sa.Column("jurisdiction", JSONB(), nullable=True, comment="{country, state, domain}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "ip_hash",
            sa.String(64),
            nullable=True,
            comment="SHA-256 of client IP for rate limiting, no PII",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_cases_created", "cases", ["created_at"], postgresql_using="btree")

    # ── Analysis (1:1 with cases) ────────────
    op.create_table(
        "analysis",
        sa.Column(
            "id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True
        ),
        sa.Column(
            "case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("timeline", JSONB(), nullable=True),
        sa.Column(
            "laws",
            JSONB(),
            nullable=True,
            comment="[{section, title, explanation, similarity_score}]",
        ),
        sa.Column("prosecution", JSONB(), nullable=True),
        sa.Column("defense", JSONB(), nullable=True),
        sa.Column("consequences", sa.Text(), nullable=True),
        sa.Column("missing_info", ARRAY(sa.Text()), nullable=True),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "raw_llm_output",
            sa.Text(),
            nullable=True,
            comment="Full LLM response for debugging/auditing",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_analysis_case", "analysis", ["case_id"], postgresql_using="btree")

    # ── Request Logs ─────────────────────────
    op.create_table(
        "request_logs",
        sa.Column(
            "id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True
        ),
        sa.Column(
            "case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("rag_latency_ms", sa.Integer(), nullable=True),
        sa.Column("llm_latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_logs_case", "request_logs", ["case_id"], postgresql_using="btree")

    # ── Feedback ─────────────────────────────
    op.create_table(
        "feedback",
        sa.Column(
            "id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True
        ),
        sa.Column(
            "case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_index("idx_logs_case", table_name="request_logs")
    op.drop_table("request_logs")
    op.drop_index("idx_analysis_case", table_name="analysis")
    op.drop_table("analysis")
    op.drop_index("idx_cases_created", table_name="cases")
    op.drop_table("cases")
