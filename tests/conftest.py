"""Shared test setup.

Settings require GROQ_API_KEY, PINECONE_API_KEY and DATABASE_URL. Tests never
reach those services: the API runs in its degraded mode (no Redis, Pinecone or
PostgreSQL) and the LLM is replaced with a stub where needed.
"""

import os

os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:1/test")

import pytest

from apps.api.services.retrieval import RetrievedLaw

HIT_AND_RUN = (
    "A speeding car hit a pedestrian near the bus stop. It was a hit and run, "
    "and the pedestrian suffered a serious injury to the leg and head."
)


def make_law(section_id: str, act: str, number: str, title: str = "") -> RetrievedLaw:
    return RetrievedLaw(
        section_id=section_id,
        act=act,
        section_number=number,
        title=title or f"{act} {number}",
        full_text="...",
        score=0.82,
    )


def llm_analysis(**overrides: object) -> dict[str, object]:
    """A schema-complete analysis as the LLM is asked to return it."""
    analysis: dict[str, object] = {
        "summary": "A driver hit a pedestrian and fled.",
        "timeline": ["Driver hits pedestrian", "Driver leaves the scene"],
        "laws": [
            {
                "section": "IPC 279",
                "title": "Rash driving",
                "explanation": "Rash or negligent driving on a public way.",
                "applies_because": "The driver was speeding.",
            }
        ],
        "prosecution": {
            "main_argument": "Rash driving caused the injury.",
            "strongest_points": ["CCTV footage"],
            "burden_of_proof": "Beyond reasonable doubt.",
        },
        "defense": {
            "main_argument": "Speed is not proven.",
            "counter_points": ["No speed measurement"],
            "possible_loopholes": ["No eyewitness"],
        },
        "consequences": {
            "criminal": "Up to 6 months",
            "civil": "Compensation claim",
            "bail_status": "Bailable",
        },
        "confidence_score": 0.9,
        "missing_info": ["Exact speed of the vehicle"],
        "disclaimer": "This analysis is AI-generated and not legal advice. Consult a qualified lawyer.",
    }
    analysis.update(overrides)
    return analysis


@pytest.fixture
def hit_and_run() -> str:
    return HIT_AND_RUN
