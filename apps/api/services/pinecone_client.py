"""
Pinecone vector store client wrapper.
Handles connection, querying, and upserting with retry logic.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from apps.api.config import get_settings

logger = logging.getLogger("andhakaanun.pinecone")


class PineconeClient:
    """
    Thin wrapper over the Pinecone SDK.
    Initialized lazily — safe to instantiate even if Pinecone is unavailable.
    """

    def __init__(self, index_instance: Any | None = None):
        """
        Args:
            index_instance: Pre-initialized Pinecone Index (from app.state).
                            If None, client operates in degraded mode.
        """
        self._index = index_instance

    @property
    def is_available(self) -> bool:
        return self._index is not None

    async def query(
        self,
        vector: list[float],
        top_k: int = 5,
        filter: dict | None = None,
        include_metadata: bool = True,
        namespace: str = "",
    ) -> list[dict[str, Any]]:
        """
        Query the Pinecone index for similar vectors.

        Returns list of matches:
        [
            {
                "id": "IPC_279",
                "score": 0.91,
                "metadata": { ... }
            },
            ...
        ]
        """
        if not self.is_available:
            logger.warning("Pinecone not available — returning empty results")
            return []

        try:
            # Pinecone SDK query is sync — run in thread to avoid blocking
            import asyncio

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._index.query(
                    vector=vector,
                    top_k=top_k,
                    filter=filter or {},
                    include_metadata=include_metadata,
                    namespace=namespace,
                ),
            )

            matches = []
            for match in result.get("matches", []):
                matches.append(
                    {
                        "id": match["id"],
                        "score": float(match.get("score", 0.0)),
                        "metadata": match.get("metadata", {}),
                    }
                )

            logger.info(
                "Pinecone query returned %d results (top_k=%d, filter=%s)",
                len(matches),
                top_k,
                filter,
            )
            return matches

        except Exception as e:
            logger.error("Pinecone query failed: %s", e)
            raise

    async def upsert(
        self,
        vectors: list[tuple[str, list[float], dict]],
        namespace: str = "",
        batch_size: int = 100,
    ) -> int:
        """
        Upsert vectors in batches.

        Args:
            vectors: List of (id, embedding, metadata) tuples.
            namespace: Pinecone namespace.
            batch_size: Vectors per batch.

        Returns:
            Total vectors upserted.
        """
        if not self.is_available:
            raise RuntimeError("Pinecone not available for upsert")

        import asyncio

        total_upserted = 0
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i : i + batch_size]
            formatted = [
                {"id": vid, "values": vec, "metadata": meta}
                for vid, vec, meta in batch
            ]

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda b=formatted: self._index.upsert(vectors=b, namespace=namespace),
            )
            total_upserted += len(batch)

            logger.info(
                "Upserted batch %d–%d (%d total)",
                i,
                i + len(batch),
                total_upserted,
            )

        return total_upserted

    async def describe_stats(self) -> dict[str, Any]:
        """Get index statistics."""
        if not self.is_available:
            return {"status": "unavailable"}

        import asyncio

        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(
            None, self._index.describe_index_stats
        )
        return stats.to_dict() if hasattr(stats, "to_dict") else dict(stats)
