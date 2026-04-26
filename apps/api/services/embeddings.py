"""
Embedding service using sentence-transformers.
Model: all-MiniLM-L6-v2 (768-dim, fast, free-tier compatible).
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Sequence

logger = logging.getLogger("andhakaanun.embeddings")

# Model name — matches PRD Section 3.2
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # MiniLM-L6-v2 is actually 384-dim, not 768


class EmbeddingService:
    """
    Manages the sentence-transformer model lifecycle.
    Lazy-loaded on first use to avoid slow startup.
    """

    def __init__(self):
        self._model = None

    def _load_model(self):
        """Load the model on first use."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading embedding model: %s", MODEL_NAME)
                self._model = SentenceTransformer(MODEL_NAME)
                logger.info(
                    "✓ Embedding model loaded (dim=%d)",
                    self._model.get_sentence_embedding_dimension(),
                )
            except ImportError:
                logger.error(
                    "sentence-transformers not installed. "
                    "Run: pip install sentence-transformers"
                )
                raise
        return self._model

    def encode_sync(
        self,
        texts: str | list[str],
        batch_size: int = 64,
        show_progress: bool = False,
        normalize: bool = True,
    ) -> list[list[float]]:
        """
        Synchronous encoding — used by embedding pipeline scripts.

        Args:
            texts: Single text or list of texts.
            batch_size: Texts per encoding batch.
            show_progress: Show tqdm progress bar.
            normalize: L2-normalize embeddings (required for cosine similarity).

        Returns:
            List of embedding vectors.
        """
        model = self._load_model()

        if isinstance(texts, str):
            texts = [texts]

        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=normalize,
        )

        return embeddings.tolist()

    async def encode(
        self,
        texts: str | list[str],
        batch_size: int = 64,
        normalize: bool = True,
    ) -> list[list[float]]:
        """
        Async encoding — offloads to thread pool to avoid blocking the event loop.
        Used in the API hot path.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.encode_sync(texts, batch_size=batch_size, normalize=normalize),
        )

    async def encode_query(self, text: str) -> list[float]:
        """
        Encode a single query string.
        Returns a single embedding vector.
        """
        embeddings = await self.encode(text)
        return embeddings[0]

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        model = self._load_model()
        return model.get_sentence_embedding_dimension()


# Singleton instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the singleton embedding service."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
