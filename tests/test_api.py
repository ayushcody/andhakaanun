"""End-to-end API flow in degraded mode, with the Groq call stubbed out.

TestClient is used without a `with` block, so the lifespan hook (which tries
to reach Redis, Pinecone and PostgreSQL) does not run. The routes then use
keyword retrieval and the in-memory case store, as they do in production when
those services are down.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.services.llm_client import LLMClient
from tests.conftest import HIT_AND_RUN, llm_analysis

client = TestClient(app)


@pytest.fixture
def stub_llm(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    prompts: list[str] = []

    async def fake(
        self: LLMClient, prompt: str, system_instruction: str | None = None
    ) -> dict[str, Any]:
        prompts.append(prompt)
        laws = [
            {"section": "IPC 279", "title": "t", "explanation": "e", "applies_because": "a"},
            {"section": "IPC 302", "title": "t", "explanation": "e", "applies_because": "a"},
        ]
        return {"data": llm_analysis(laws=laws), "model": "stub", "latency_ms": 1}

    monkeypatch.setattr(LLMClient, "generate_with_fallback", fake)
    return prompts


def test_detect_jurisdiction_endpoint() -> None:
    res = client.post("/detect-jurisdiction", json={"text": HIT_AND_RUN})
    assert res.status_code == 200
    assert {"section": "IPC_279", "label": "IPC 279"} in res.json()["badges"]


def test_short_case_text_is_rejected_with_suggestions() -> None:
    res = client.post("/analyze-case", json={"case_text": "too short", "location": "Pune"})
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["error"] == "INSUFFICIENT_CONTEXT"
    assert detail["min_length"] == 50


def test_analyze_fetch_and_refine_a_case(stub_llm: list[str]) -> None:
    res = client.post("/analyze-case", json={"case_text": HIT_AND_RUN, "location": "Pune"})
    assert res.status_code == 200, res.text
    analysis = res.json()
    case_id = analysis["case_id"]

    # The section the model invented (IPC 302) was not retrieved, so it is dropped.
    assert [law["section"] for law in analysis["laws"]] == ["IPC 279"]
    assert analysis["confidence_score"] == 0.8
    assert analysis["missing_info"] == ["Exact speed of the vehicle"]

    stored = client.get(f"/cases/{case_id}")
    assert stored.status_code == 200
    assert stored.json()["analysis"]["summary"] == analysis["summary"]

    answers = [{"question": "Exact speed of the vehicle", "answer": "About 80 km/h"}]
    refined = client.post(f"/cases/{case_id}/refine", json={"answers": answers})
    assert refined.status_code == 200, refined.text

    # The follow-up answer is appended to the narrative before re-analysis.
    assert "A: About 80 km/h" in stub_llm[-1]
    assert "About 80 km/h" in client.get(f"/cases/{case_id}").json()["input_text"]


def test_unknown_case_returns_404() -> None:
    res = client.get("/cases/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
