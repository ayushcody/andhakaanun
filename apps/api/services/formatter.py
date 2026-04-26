"""
Response formatter service.
Transforms raw analysis output into validated API response schemas.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from apps.api.models.schemas import (
    AnalysisResponse,
    ConsequencesDetail,
    DefenseDetail,
    LawDetail,
    ProsecutionDetail,
)
from apps.api.services.retrieval import RetrievedLaw

logger = logging.getLogger("andhakaanun.formatter")

MANDATORY_DISCLAIMER = (
    "This analysis is AI-generated and not legal advice. Consult a qualified lawyer."
)


def format_analysis_response(
    case_id: UUID,
    raw_llm_output: dict[str, Any],
    retrieved_laws: list[RetrievedLaw],
    from_cache: bool = False,
) -> AnalysisResponse:
    """
    Transform raw LLM JSON + retrieval metadata into a validated AnalysisResponse.

    Args:
        case_id: UUID of the case.
        raw_llm_output: Parsed and validated LLM output dict.
        retrieved_laws: Laws from RAG retrieval (for enrichment).
        from_cache: Whether the result came from cache.

    Returns:
        Fully validated AnalysisResponse.
    """
    # Build law details with similarity scores
    laws = []
    score_map = {law.section_id: law.score for law in retrieved_laws}

    for law_data in raw_llm_output.get("laws", []):
        section = law_data.get("section", "")
        # Try to find matching score from RAG results
        normalized = section.upper().replace(" ", "_")
        score = score_map.get(normalized, law_data.get("similarity_score", 0.5))

        laws.append(
            LawDetail(
                section=section,
                title=law_data.get("title", ""),
                explanation=law_data.get("explanation", ""),
                applies_because=law_data.get("applies_because", ""),
                similarity_score=min(max(float(score), 0.0), 1.0),
            )
        )

    # Build prosecution detail
    prosecution_data = raw_llm_output.get("prosecution", {})
    prosecution = ProsecutionDetail(
        main_argument=prosecution_data.get("main_argument", "Not determined"),
        strongest_points=prosecution_data.get("strongest_points", []),
        burden_of_proof=prosecution_data.get("burden_of_proof", "Not determined"),
    )

    # Build defense detail
    defense_data = raw_llm_output.get("defense", {})
    defense = DefenseDetail(
        main_argument=defense_data.get("main_argument", "Not determined"),
        counter_points=defense_data.get("counter_points", []),
        possible_loopholes=defense_data.get("possible_loopholes", []),
    )

    # Build consequences detail
    consequences_data = raw_llm_output.get("consequences", {})
    consequences = ConsequencesDetail(
        criminal=consequences_data.get("criminal", "Not determined"),
        civil=consequences_data.get("civil", "Not determined"),
        bail_status=consequences_data.get("bail_status", "Not determined"),
    )

    return AnalysisResponse(
        case_id=case_id,
        summary=raw_llm_output.get("summary", "Analysis could not generate a summary."),
        timeline=raw_llm_output.get("timeline", []),
        laws=laws,
        prosecution=prosecution,
        defense=defense,
        consequences=consequences,
        confidence_score=min(
            max(float(raw_llm_output.get("confidence_score", 0.3)), 0.0), 1.0
        ),
        missing_info=raw_llm_output.get("missing_info", []),
        from_cache=from_cache,
        disclaimer=raw_llm_output.get("disclaimer", MANDATORY_DISCLAIMER),
    )


def format_for_logging(
    case_id: UUID,
    analysis: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Format analysis result for structured logging.
    Matches PRD §10 observability spec.
    """
    return {
        "event": "analysis_complete",
        "case_id": str(case_id),
        "rag_ms": metadata.get("rag_latency_ms", 0),
        "llm_ms": metadata.get("llm_latency_ms", 0),
        "total_ms": metadata.get("total_latency_ms", 0),
        "confidence": analysis.get("confidence_score", 0),
        "laws_retrieved": len(analysis.get("laws", [])),
        "from_cache": metadata.get("from_cache", False),
        "model": metadata.get("model_version"),
        "token_count": metadata.get("token_count", 0),
    }
