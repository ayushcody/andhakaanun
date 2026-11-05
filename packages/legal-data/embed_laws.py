"""
Legal data embedding pipeline.
Reads structured law data, generates embeddings, and upserts to Pinecone.

Usage:
  PYTHONPATH=. python packages/legal-data/embed_laws.py

Matches PRD §8.2 — Chunking Strategy.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.config import get_settings
from apps.api.services.embeddings import get_embedding_service
from apps.api.services.pinecone_client import PineconeClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("embed_pipeline")


def prepare_chunk(section: dict) -> str:
    """
    Build a metadata-enriched text chunk for embedding.
    Matches PRD §8.2 chunking strategy exactly.
    """
    return (
        f"ACT: {section['act']}\n"
        f"SECTION: {section['number']} - {section['title']}\n"
        f"DOMAIN: {section['domain']}\n"
        f"TEXT: {section['full_text']}\n"
        f"SIMPLIFIED: {section.get('simplified_explanation', section.get('simplified', ''))}\n"
        f"KEYWORDS: {', '.join(section.get('trigger_keywords', section.get('keywords', [])))}"
    )


def build_metadata(section: dict) -> dict:
    """
    Build Pinecone metadata for a law section.
    Matches PRD §3.2 vector metadata schema.
    """
    return {
        "section_id": section["section_id"],
        "act": section["act"],
        "section_number": section["number"],
        "title": section["title"],
        "full_text": section["full_text"],
        "simplified": section.get("simplified_explanation", section.get("simplified", "")),
        "domain": section["domain"],
        "max_punishment": section.get("max_punishment", ""),
        "bailable": section.get("bailable", False),
        "cognizable": section.get("cognizable", False),
    }


async def run_pipeline(data_path: str, batch_size: int = 64):
    """
    Main embedding pipeline:
    1. Load law data from JSON
    2. Prepare chunks
    3. Generate embeddings
    4. Upsert to Pinecone in batches
    """
    settings = get_settings()

    # Load data
    data_file = Path(data_path)
    if not data_file.exists():
        logger.error("Data file not found: %s", data_path)
        logger.info("Using fallback store data for demo...")

        # Use the fallback store as seed data
        from apps.api.services.fallback_store import FALLBACK_LAWS

        sections = []
        for law in FALLBACK_LAWS.values():
            sections.append(
                {
                    "section_id": law.section_id,
                    "act": law.act,
                    "number": law.section_number,
                    "title": law.title,
                    "full_text": law.full_text,
                    "simplified": law.simplified,
                    "domain": law.domain,
                    "max_punishment": law.max_punishment,
                    "bailable": law.bailable,
                    "cognizable": law.cognizable,
                    "keywords": law.keywords,
                }
            )
    else:
        with open(data_file) as f:
            sections = json.load(f)

    logger.info("Loaded %d law sections", len(sections))

    # Prepare text chunks
    chunks = [prepare_chunk(s) for s in sections]
    logger.info("Prepared %d text chunks for embedding", len(chunks))

    # Generate embeddings
    embedding_service = get_embedding_service()
    logger.info("Encoding %d chunks (batch_size=%d)...", len(chunks), batch_size)
    embeddings = embedding_service.encode_sync(chunks, batch_size=batch_size, show_progress=True)
    logger.info("✓ Generated %d embeddings (dim=%d)", len(embeddings), len(embeddings[0]))

    # Connect to Pinecone
    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=settings.pinecone_api_key)
        index = pc.Index(settings.pinecone_index)
        client = PineconeClient(index)
    except Exception as e:
        logger.error("Failed to connect to Pinecone: %s", e)
        logger.info("Saving embeddings to local file instead...")

        # Save embeddings locally for later upload
        output = []
        for i, section in enumerate(sections):
            output.append(
                {
                    "id": section["section_id"],
                    "values": embeddings[i],
                    "metadata": build_metadata(section),
                }
            )

        output_path = PROJECT_ROOT / "packages" / "legal-data" / "embeddings_output.json"
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
        logger.info("✓ Saved %d embeddings to %s", len(output), output_path)
        return

    # Prepare upsert vectors
    vectors: list[tuple[str, list[float], dict[str, Any]]] = []
    for i, section in enumerate(sections):
        vectors.append(
            (
                str(section["section_id"]),
                embeddings[i],
                build_metadata(section),
            )
        )

    # Upsert to Pinecone
    total = await client.upsert(vectors, batch_size=100)
    logger.info("✓ Upserted %d vectors to Pinecone index: %s", total, settings.pinecone_index)

    # Verify
    stats = await client.describe_stats()
    logger.info("Index stats: %s", stats)


if __name__ == "__main__":
    data_path = sys.argv[1] if len(sys.argv) > 1 else "packages/legal-data/laws.json"
    asyncio.run(run_pipeline(data_path))
