"""
Output validation and hallucination guard.

Validates LLM JSON output against expected schema and ensures
no hallucinated laws (laws not present in the provided context).

Matches PRD §5.1 Rule 1: "Use ONLY the provided legal context."
"""

from __future__ import annotations

import logging
from typing import Any

from apps.api.services.retrieval import RetrievedLaw

logger = logging.getLogger("andhakaanun.validation")


# ──────────────────────────────────────────────
# Required fields in LLM output
# ──────────────────────────────────────────────

REQUIRED_FIELDS = {
    "summary": str,
    "timeline": list,
    "laws": list,
    "prosecution": dict,
    "defense": dict,
    "consequences": dict,
    "confidence_score": (int, float),
    "missing_info": list,
    "disclaimer": str,
}

REQUIRED_LAW_FIELDS = {"section", "title", "explanation", "applies_because"}

REQUIRED_PROSECUTION_FIELDS = {"main_argument", "strongest_points", "burden_of_proof"}

REQUIRED_DEFENSE_FIELDS = {"main_argument", "counter_points", "possible_loopholes"}

REQUIRED_CONSEQUENCES_FIELDS = {"criminal", "civil", "bail_status"}

MANDATORY_DISCLAIMER = "This analysis is AI-generated and not legal advice. Consult a qualified lawyer."


# ──────────────────────────────────────────────
# Schema Validation
# ──────────────────────────────────────────────

def validate_schema(output: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate that the LLM output matches the expected JSON schema.

    Returns:
        (is_valid, list_of_issues)
    """
    issues: list[str] = []

    # Check top-level required fields
    for field_name, expected_type in REQUIRED_FIELDS.items():
        if field_name not in output:
            issues.append(f"Missing required field: {field_name}")
        elif not isinstance(output[field_name], expected_type):
            issues.append(
                f"Field '{field_name}' has wrong type: "
                f"expected {expected_type}, got {type(output[field_name])}"
            )

    # Validate laws array
    if "laws" in output and isinstance(output["laws"], list):
        for i, law in enumerate(output["laws"]):
            if not isinstance(law, dict):
                issues.append(f"laws[{i}] is not a dict")
                continue
            missing = REQUIRED_LAW_FIELDS - set(law.keys())
            if missing:
                issues.append(f"laws[{i}] missing fields: {missing}")

    # Validate prosecution
    if "prosecution" in output and isinstance(output["prosecution"], dict):
        missing = REQUIRED_PROSECUTION_FIELDS - set(output["prosecution"].keys())
        if missing:
            issues.append(f"prosecution missing fields: {missing}")

    # Validate defense
    if "defense" in output and isinstance(output["defense"], dict):
        missing = REQUIRED_DEFENSE_FIELDS - set(output["defense"].keys())
        if missing:
            issues.append(f"defense missing fields: {missing}")

    # Validate consequences
    if "consequences" in output and isinstance(output["consequences"], dict):
        missing = REQUIRED_CONSEQUENCES_FIELDS - set(output["consequences"].keys())
        if missing:
            issues.append(f"consequences missing fields: {missing}")

    # Validate confidence_score range
    if "confidence_score" in output:
        score = output["confidence_score"]
        if isinstance(score, (int, float)) and not (0.0 <= score <= 1.0):
            issues.append(f"confidence_score out of range: {score} (must be 0.0–1.0)")

    is_valid = len(issues) == 0
    if not is_valid:
        logger.warning("Schema validation failed: %d issues", len(issues))
        for issue in issues:
            logger.warning("  → %s", issue)

    return is_valid, issues


# ──────────────────────────────────────────────
# Hallucination Guard
# ──────────────────────────────────────────────

def check_hallucinated_laws(
    output: dict[str, Any],
    context_laws: list[RetrievedLaw],
) -> tuple[list[dict], list[dict]]:
    """
    Check if the LLM cited any laws not present in the provided context.
    This is the core hallucination guard per PRD §5.1 Rule 1.

    Args:
        output: Parsed LLM JSON output.
        context_laws: Laws that were provided in the prompt context.

    Returns:
        (valid_laws, hallucinated_laws)
    """
    if "laws" not in output or not isinstance(output["laws"], list):
        return [], []

    # Build set of context section IDs (normalized)
    context_ids = set()
    for law in context_laws:
        context_ids.add(law.section_id.upper().replace(" ", "_"))
        # Also add common format variations
        context_ids.add(f"{law.act}_{law.section_number}".upper())
        context_ids.add(f"{law.act} {law.section_number}".upper())

    valid_laws: list[dict] = []
    hallucinated: list[dict] = []

    for cited_law in output["laws"]:
        if not isinstance(cited_law, dict):
            continue

        section = cited_law.get("section", "").strip()
        # Normalize the cited section for comparison
        normalized = section.upper().replace(" ", "_")
        alt_normalized = section.upper()

        if normalized in context_ids or alt_normalized in context_ids:
            valid_laws.append(cited_law)
        else:
            hallucinated.append(cited_law)
            logger.warning(
                "HALLUCINATION DETECTED: LLM cited '%s' which is not in provided context",
                section,
            )

    if hallucinated:
        logger.warning(
            "Hallucination guard: %d/%d laws are hallucinated",
            len(hallucinated),
            len(output["laws"]),
        )

    return valid_laws, hallucinated


# ──────────────────────────────────────────────
# Full Validation Pipeline
# ──────────────────────────────────────────────

def validate_and_clean(
    output: dict[str, Any],
    context_laws: list[RetrievedLaw],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Full validation pipeline:
    1. Schema validation (fix missing fields with defaults)
    2. Hallucination guard (remove hallucinated laws)
    3. Ensure disclaimer is present
    4. Clamp confidence score

    Args:
        output: Raw parsed LLM output.
        context_laws: Laws provided in prompt context.

    Returns:
        (cleaned_output, validation_metadata)
    """
    metadata: dict[str, Any] = {
        "schema_valid": True,
        "schema_issues": [],
        "hallucinated_count": 0,
        "hallucinated_laws": [],
        "original_law_count": 0,
        "final_law_count": 0,
        "confidence_adjusted": False,
    }

    # 1. Schema validation
    is_valid, issues = validate_schema(output)
    metadata["schema_valid"] = is_valid
    metadata["schema_issues"] = issues

    # Fix missing fields with sensible defaults
    cleaned = _apply_defaults(output)

    # 2. Hallucination guard
    if context_laws:
        valid_laws, hallucinated = check_hallucinated_laws(cleaned, context_laws)
        metadata["original_law_count"] = len(cleaned.get("laws", []))
        metadata["hallucinated_count"] = len(hallucinated)
        metadata["hallucinated_laws"] = [h.get("section", "?") for h in hallucinated]
        metadata["final_law_count"] = len(valid_laws)

        # Replace laws with only valid ones
        cleaned["laws"] = valid_laws

        # Adjust confidence if hallucinations were found
        if hallucinated:
            original_score = cleaned.get("confidence_score", 0.5)
            penalty = len(hallucinated) * 0.1
            adjusted = max(original_score - penalty, 0.1)
            cleaned["confidence_score"] = round(adjusted, 2)
            metadata["confidence_adjusted"] = True
            logger.info(
                "Confidence adjusted: %.2f → %.2f (-%d hallucinated laws)",
                original_score, adjusted, len(hallucinated),
            )

    # 3. Ensure disclaimer
    cleaned["disclaimer"] = MANDATORY_DISCLAIMER

    # 4. Clamp confidence score
    if "confidence_score" in cleaned:
        cleaned["confidence_score"] = round(
            min(max(float(cleaned["confidence_score"]), 0.0), 1.0), 2
        )

    return cleaned, metadata


def _apply_defaults(output: dict[str, Any]) -> dict[str, Any]:
    """Apply default values for missing fields."""
    defaults = {
        "summary": "Analysis could not generate a full summary.",
        "timeline": [],
        "laws": [],
        "prosecution": {
            "main_argument": "Not determined",
            "strongest_points": [],
            "burden_of_proof": "Not determined",
        },
        "defense": {
            "main_argument": "Not determined",
            "counter_points": [],
            "possible_loopholes": [],
        },
        "consequences": {
            "criminal": "Not determined",
            "civil": "Not determined",
            "bail_status": "Not determined",
        },
        "confidence_score": 0.3,
        "missing_info": ["Some analysis fields could not be determined"],
        "disclaimer": MANDATORY_DISCLAIMER,
    }

    result = dict(defaults)
    result.update(output)

    # Ensure nested dicts have all required fields
    for key in ("prosecution", "defense", "consequences"):
        if key in result and isinstance(result[key], dict):
            for sub_key, sub_val in defaults[key].items():
                if sub_key not in result[key]:
                    result[key][sub_key] = sub_val

    return result
