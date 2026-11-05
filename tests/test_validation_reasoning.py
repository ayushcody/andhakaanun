"""Output validation, the hallucination guard and the reasoning engine."""

from typing import Any

from apps.api.services.reasoning import ReasoningEngine
from apps.api.services.validation import (
    MANDATORY_DISCLAIMER,
    validate_and_clean,
    validate_schema,
)
from tests.conftest import llm_analysis, make_law

CONTEXT = [make_law("IPC_279", "IPC", "279"), make_law("MVA_184", "MVA", "184")]


def test_validate_schema_accepts_complete_output() -> None:
    ok, issues = validate_schema(llm_analysis())
    assert ok, issues


def test_validate_schema_reports_missing_fields_and_bad_score() -> None:
    output = llm_analysis(confidence_score=1.7)
    del output["defense"]
    ok, issues = validate_schema(output)
    assert not ok
    assert any("defense" in i for i in issues)
    assert any("confidence_score out of range" in i for i in issues)


def test_hallucinated_sections_are_removed_and_confidence_lowered() -> None:
    laws = [
        {"section": "IPC 279", "title": "t", "explanation": "e", "applies_because": "a"},
        {"section": "IPC 302", "title": "t", "explanation": "e", "applies_because": "a"},
    ]
    cleaned, meta = validate_and_clean(llm_analysis(laws=laws, confidence_score=0.9), CONTEXT)
    assert [law["section"] for law in cleaned["laws"]] == ["IPC 279"]
    assert meta["hallucinated_laws"] == ["IPC 302"]
    assert cleaned["confidence_score"] == 0.8


def test_confidence_penalty_never_goes_below_floor() -> None:
    laws = [
        {"section": f"IPC {n}", "title": "t", "explanation": "e", "applies_because": "a"}
        for n in (300, 301, 302)
    ]
    cleaned, _ = validate_and_clean(llm_analysis(laws=laws, confidence_score=0.2), CONTEXT)
    assert cleaned["laws"] == []
    assert cleaned["confidence_score"] == 0.1


def test_missing_fields_get_defaults_and_disclaimer_is_enforced() -> None:
    cleaned, meta = validate_and_clean(
        {"summary": "Only a summary", "disclaimer": "anything"}, CONTEXT
    )
    assert meta["schema_valid"] is False
    assert cleaned["prosecution"]["burden_of_proof"] == "Not determined"
    assert cleaned["defense"]["possible_loopholes"] == []
    assert cleaned["disclaimer"] == MANDATORY_DISCLAIMER


class StubLLM:
    """Stands in for LLMClient.generate_with_fallback."""

    def __init__(self, data: Any = None, error: Exception | None = None) -> None:
        self.data = data
        self.error = error
        self.prompts: list[str] = []

    async def generate_with_fallback(
        self, prompt: str, system_instruction: str | None = None
    ) -> dict[str, Any]:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return {"data": self.data, "model": "stub", "latency_ms": 1, "token_count": 42}


async def analyze(llm: StubLLM) -> dict[str, Any]:
    engine = ReasoningEngine(llm_client=llm)  # type: ignore[arg-type]
    return await engine.analyze("A car hit a pedestrian.", "Pune", ["traffic_criminal"], CONTEXT)


async def test_reasoning_puts_retrieved_sections_in_the_prompt() -> None:
    llm = StubLLM(llm_analysis())
    result = await analyze(llm)
    assert "<legal_context>" in llm.prompts[0]
    assert "[IPC_279]" in llm.prompts[0]
    assert result["metadata"]["model"] == "stub"


async def test_reasoning_copies_retrieval_scores_onto_cited_sections() -> None:
    result = await analyze(StubLLM(llm_analysis()))
    assert result["analysis"]["laws"][0]["similarity_score"] == 0.82


async def test_reasoning_unwraps_a_one_object_json_array() -> None:
    result = await analyze(StubLLM([llm_analysis(summary="wrapped")]))
    assert result["analysis"]["summary"] == "wrapped"
    assert result["metadata"]["partial_response"] is False


async def test_reasoning_returns_partial_result_when_llm_fails() -> None:
    result = await analyze(StubLLM(error=RuntimeError("both models failed")))
    analysis = result["analysis"]
    assert result["metadata"]["partial_response"] is True
    assert analysis["confidence_score"] == 0.15
    assert {law["section"] for law in analysis["laws"]} == {"IPC 279", "MVA 184"}


async def test_reasoning_treats_non_object_output_as_failure() -> None:
    result = await analyze(StubLLM("not json"))
    assert result["metadata"]["partial_response"] is True
