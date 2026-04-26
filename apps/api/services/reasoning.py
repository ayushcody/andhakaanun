"""
LLM Reasoning Engine — Orchestrates the full analysis pipeline.

Flow:
  1. Build system + user prompts
  2. Call Groq with fallback chain
  3. Validate JSON output
  4. Run hallucination guard
  5. Return cleaned analysis

Matches PRD §5 end-to-end.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from apps.api.services.llm_client import LLMClient, get_llm_client
from apps.api.services.prompts import (
    SYSTEM_PROMPT,
    build_partial_response,
    build_user_prompt,
)
from apps.api.services.retrieval import RetrievedLaw
from apps.api.services.validation import validate_and_clean

logger = logging.getLogger("andhakaanun.reasoning")


class ReasoningEngine:
    """
    Orchestrates LLM-based legal reasoning with:
    - Structured prompt construction
    - Primary + fallback model chain
    - Output validation and hallucination guard
    - Graceful degradation to partial RAG results
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self._llm = llm_client or get_llm_client()

    async def analyze(
        self,
        case_text: str,
        location: str,
        domains: list[str],
        retrieved_laws: list[RetrievedLaw],
    ) -> dict[str, Any]:
        """
        Full reasoning pipeline.

        Args:
            case_text: The case narrative.
            location: Incident location.
            domains: Detected legal domains.
            retrieved_laws: Laws retrieved from RAG pipeline.

        Returns:
            Dict with keys:
              - analysis: Cleaned analysis result
              - metadata: Pipeline metadata (latency, model, validation info)
        """
        start = time.perf_counter()

        metadata: dict[str, Any] = {
            "model": None,
            "llm_latency_ms": 0,
            "total_latency_ms": 0,
            "token_count": 0,
            "fallback_used": False,
            "partial_response": False,
            "validation": {},
        }

        # 1. Build prompts
        user_prompt = build_user_prompt(
            case_text=case_text,
            location=location,
            domains=domains,
            retrieved_laws=retrieved_laws,
        )

        logger.info(
            "Built prompt: %d chars, %d laws in context, domains=%s",
            len(user_prompt),
            len(retrieved_laws),
            domains,
        )

        # 2. Call LLM with fallback chain
        try:
            result = await self._llm.generate_with_fallback(
                prompt=user_prompt,
                system_instruction=SYSTEM_PROMPT,
            )

            raw_output = result["data"]
            metadata["model"] = result["model"]
            metadata["llm_latency_ms"] = result["latency_ms"]
            metadata["token_count"] = result.get("token_count", 0)
            metadata["fallback_used"] = result.get("fallback_used", False)

        except Exception as e:
            # Both models failed — return partial RAG results
            logger.error("All LLM models failed: %s — returning partial results", e)
            partial = build_partial_response(
                case_text=case_text,
                retrieved_laws=retrieved_laws,
                error_reason=str(e),
            )
            metadata["partial_response"] = True
            metadata["total_latency_ms"] = int(
                (time.perf_counter() - start) * 1000
            )
            return {
                "analysis": partial,
                "metadata": metadata,
            }

        # 3. Validate and clean output
        cleaned, validation_meta = validate_and_clean(
            output=raw_output,
            context_laws=retrieved_laws,
        )

        metadata["validation"] = validation_meta

        # 4. Add similarity scores to laws from RAG results
        cleaned["laws"] = self._enrich_laws_with_scores(
            cleaned.get("laws", []),
            retrieved_laws,
        )

        metadata["total_latency_ms"] = int(
            (time.perf_counter() - start) * 1000
        )

        logger.info(
            "Reasoning complete: model=%s, laws=%d, confidence=%.2f, latency=%dms",
            metadata["model"],
            len(cleaned.get("laws", [])),
            cleaned.get("confidence_score", 0),
            metadata["total_latency_ms"],
        )

        return {
            "analysis": cleaned,
            "metadata": metadata,
        }

    @staticmethod
    def _enrich_laws_with_scores(
        llm_laws: list[dict],
        context_laws: list[RetrievedLaw],
    ) -> list[dict]:
        """
        Add similarity_score from RAG results to LLM-output laws.
        """
        # Build lookup: section_id → score
        score_map: dict[str, float] = {}
        for law in context_laws:
            score_map[law.section_id.upper().replace(" ", "_")] = law.score
            score_map[f"{law.act} {law.section_number}".upper()] = law.score
            score_map[f"{law.act}_{law.section_number}".upper()] = law.score

        enriched = []
        for law in llm_laws:
            section = law.get("section", "").strip()
            normalized = section.upper().replace(" ", "_")
            alt = section.upper()

            score = score_map.get(normalized) or score_map.get(alt) or 0.5
            law["similarity_score"] = round(score, 2)
            enriched.append(law)

        return enriched


# ──────────────────────────────────────────────
# Convenience Function
# ──────────────────────────────────────────────

async def run_reasoning(
    case_text: str,
    location: str,
    domains: list[str],
    retrieved_laws: list[RetrievedLaw],
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    """
    Convenience wrapper — creates engine and runs analysis.
    Used by API endpoints.
    """
    engine = ReasoningEngine(llm_client=llm_client)
    return await engine.analyze(
        case_text=case_text,
        location=location,
        domains=domains,
        retrieved_laws=retrieved_laws,
    )
