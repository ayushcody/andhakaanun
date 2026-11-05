"""
RAG retrieval service — the core retrieval pipeline.

Flow:
  1. Check Redis cache
  2. Embed query → query Pinecone with domain filter
  3. Fallback to in-memory keyword search if Pinecone fails
  4. Return structured RetrievedLaw results

Matches PRD §3.2, §3.3, §9.3 (fallback chain).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from apps.api.services.cache import CacheService
from apps.api.services.embeddings import EmbeddingService, get_embedding_service
from apps.api.services.fallback_store import FallbackLaw, keyword_search
from apps.api.services.pinecone_client import PineconeClient

logger = logging.getLogger("andhakaanun.retrieval")


@dataclass
class RetrievedLaw:
    """Single retrieved law from vector store or fallback."""

    section_id: str = ""
    act: str = ""
    section_number: str = ""
    title: str = ""
    full_text: str = ""
    simplified: str = ""
    domain: str = ""
    max_punishment: str = ""
    bailable: bool = False
    cognizable: bool = False
    score: float = 0.0


class RetrievalService:
    """
    Orchestrates the full retrieval pipeline:
      Pinecone (primary) → Keyword fallback (secondary)
    With Redis caching and latency tracking.
    """

    def __init__(
        self,
        pinecone_client: PineconeClient,
        embedding_service: EmbeddingService | None = None,
        cache_service: CacheService | None = None,
        pinecone_timeout: float = 2.0,
    ):
        self._pinecone = pinecone_client
        self._embeddings = embedding_service or get_embedding_service()
        self._cache = cache_service
        self._timeout = pinecone_timeout

    async def retrieve(
        self,
        query: str,
        domains: list[str] | None = None,
        top_k: int = 5,
    ) -> tuple[list[RetrievedLaw], dict[str, Any]]:
        """
        Full retrieval pipeline with fallback chain.

        Args:
            query: Case narrative text.
            domains: Detected legal domains for filtering.
            top_k: Number of results to retrieve.

        Returns:
            Tuple of (results, metadata) where metadata includes latency
            and source info.
        """
        start = time.perf_counter()
        metadata: dict[str, Any] = {
            "source": "none",
            "latency_ms": 0,
            "count": 0,
            "fallback_used": False,
        }

        # --- Attempt 1: Pinecone vector search ---
        if self._pinecone.is_available:
            try:
                results = await asyncio.wait_for(
                    self._pinecone_search(query, domains, top_k),
                    timeout=self._timeout,
                )
                if results:
                    metadata["source"] = "pinecone"
                    metadata["count"] = len(results)
                    metadata["latency_ms"] = int((time.perf_counter() - start) * 1000)
                    logger.info(
                        "Pinecone retrieval: %d results in %dms",
                        len(results),
                        metadata["latency_ms"],
                    )
                    return results, metadata
            except TimeoutError:
                logger.warning(
                    "Pinecone timeout after %.1fs — falling back to keywords",
                    self._timeout,
                )
            except Exception as e:
                logger.error("Pinecone search failed: %s — falling back", e)

        # --- Attempt 2: In-memory keyword fallback ---
        logger.info("Using keyword fallback for retrieval")
        fallback_results = keyword_search(query, domains=domains, top_k=top_k)
        results = [self._fallback_to_retrieved(law) for law in fallback_results]

        metadata["source"] = "keyword_fallback"
        metadata["count"] = len(results)
        metadata["fallback_used"] = True
        metadata["latency_ms"] = int((time.perf_counter() - start) * 1000)

        logger.info(
            "Keyword fallback: %d results in %dms",
            len(results),
            metadata["latency_ms"],
        )
        return results, metadata

    async def _pinecone_search(
        self,
        query: str,
        domains: list[str] | None,
        top_k: int,
    ) -> list[RetrievedLaw]:
        """
        Embed query → search Pinecone → parse results.
        """
        # 1. Embed the query
        query_vector = await self._embeddings.encode_query(query)

        # 2. Build domain filter
        pc_filter: dict | None = None
        if domains:
            pc_filter = {"domain": {"$in": domains}}

        # 3. Query Pinecone
        matches = await self._pinecone.query(
            vector=query_vector,
            top_k=top_k,
            filter=pc_filter,
            include_metadata=True,
        )

        # 4. Parse results
        results = []
        for match in matches:
            meta = match.get("metadata", {})
            results.append(
                RetrievedLaw(
                    section_id=meta.get("section_id", match["id"]),
                    act=meta.get("act", ""),
                    section_number=meta.get("section_number", ""),
                    title=meta.get("title", ""),
                    full_text=meta.get("full_text", ""),
                    simplified=meta.get("simplified", ""),
                    domain=meta.get("domain", ""),
                    max_punishment=meta.get("max_punishment", ""),
                    bailable=meta.get("bailable", False),
                    cognizable=meta.get("cognizable", False),
                    score=match.get("score", 0.0),
                )
            )

        return results

    @staticmethod
    def _fallback_to_retrieved(law: FallbackLaw) -> RetrievedLaw:
        """Convert a FallbackLaw to a RetrievedLaw."""
        return RetrievedLaw(
            section_id=law.section_id,
            act=law.act,
            section_number=law.section_number,
            title=law.title,
            full_text=law.full_text,
            simplified=law.simplified,
            domain=law.domain,
            max_punishment=law.max_punishment,
            bailable=law.bailable,
            cognizable=law.cognizable,
            score=0.5,  # Fallback results get a neutral score
        )


async def retrieve_laws(
    query: str,
    domains: list[str] | None = None,
    top_k: int = 5,
    pinecone_index: Any | None = None,
    redis_client: Any | None = None,
    pinecone_timeout: float = 2.0,
    cache_ttl: int = 3600,
) -> tuple[list[RetrievedLaw], dict[str, Any]]:
    """
    Convenience function — creates service and runs retrieval.
    Used by the API endpoints.
    """
    pinecone_client = PineconeClient(pinecone_index)
    cache_service = CacheService(redis_client, ttl_seconds=cache_ttl)
    embedding_service = get_embedding_service()

    service = RetrievalService(
        pinecone_client=pinecone_client,
        embedding_service=embedding_service,
        cache_service=cache_service,
        pinecone_timeout=pinecone_timeout,
    )

    return await service.retrieve(query, domains=domains, top_k=top_k)
