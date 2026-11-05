"""
Prompt engineering module — System and User prompt construction.

Matches PRD §5.1 (System Prompt) and §5.2 (User Message Template) exactly.
"""

from __future__ import annotations

from apps.api.services.retrieval import RetrievedLaw

# ──────────────────────────────────────────────
# System Prompt (PRD §5.1 — verbatim)
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """You are a legal reasoning assistant specializing in Indian law.

RULES (non-negotiable):
1. Use ONLY the provided legal context. Do not cite any law not present in <legal_context>.
2. If a law is not in <legal_context>, say "Insufficient legal context" for that field.
3. Output ONLY valid JSON matching the schema below. No markdown, no preamble.
4. Set confidence_score lower if: input is vague, fewer than 2 laws retrieved, or facts are ambiguous.
5. Include mandatory disclaimer verbatim.

OUTPUT SCHEMA:
{
  "summary": "string (2-4 sentences, plain English)",
  "timeline": ["string", ...],
  "laws": [{"section": "IPC 279", "title": "...", "explanation": "...", "applies_because": "..."}],
  "prosecution": {"main_argument": "string", "strongest_points": ["string"], "burden_of_proof": "string"},
  "defense": {"main_argument": "string", "counter_points": ["string"], "possible_loopholes": ["string"]},
  "consequences": {"criminal": "string", "civil": "string", "bail_status": "string"},
  "confidence_score": 0.0-1.0,
  "missing_info": ["string"],
  "disclaimer": "This analysis is AI-generated and not legal advice. Consult a qualified lawyer."
}

IMPORTANT: Respond with a single valid JSON object only. No text outside the JSON."""


# ──────────────────────────────────────────────
# User Prompt Template (PRD §5.2)
# ──────────────────────────────────────────────


def build_user_prompt(
    case_text: str,
    location: str,
    domains: list[str],
    retrieved_laws: list[RetrievedLaw],
) -> str:
    """
    Construct the user prompt with case narrative, jurisdiction context,
    and retrieved legal context.

    Matches PRD §5.2 template exactly.
    """
    # Format retrieved laws
    legal_context_lines = []
    for law in retrieved_laws:
        line = f"[{law.section_id}] {law.title}: {law.full_text}"
        if law.simplified:
            line += f"\nSimplified: {law.simplified}"
        if law.max_punishment:
            line += f"\nMax Punishment: {law.max_punishment}"
        if law.bailable is not None:
            line += f"\nBailable: {'Yes' if law.bailable else 'No'}"
        if law.cognizable is not None:
            line += f"\nCognizable: {'Yes' if law.cognizable else 'No'}"
        legal_context_lines.append(line)

    legal_context = (
        "\n\n".join(legal_context_lines)
        if legal_context_lines
        else "No relevant laws found in the context."
    )

    domain_str = ", ".join(domains) if domains else "Unknown"

    return f"""<case_narrative>
{case_text}
</case_narrative>

<detected_jurisdiction>
Country: India | State: {location or "Not specified"} | Domain: {domain_str}
</detected_jurisdiction>

<legal_context>
{legal_context}
</legal_context>

Analyze this case and return the JSON output."""


# ──────────────────────────────────────────────
# Fallback partial response (PRD §9.3)
# ──────────────────────────────────────────────


def build_partial_response(
    case_text: str,
    retrieved_laws: list[RetrievedLaw],
    error_reason: str,
) -> dict:
    """
    When both LLM models fail, return partial RAG results with disclaimer.
    This is the last fallback in the chain per PRD §9.3.
    """
    laws = []
    for law in retrieved_laws:
        laws.append(
            {
                "section": f"{law.act} {law.section_number}",
                "title": law.title,
                "explanation": law.simplified or law.full_text[:200],
                "applies_because": "Matched via keyword retrieval (LLM analysis unavailable)",
                "similarity_score": law.score,
            }
        )

    return {
        "summary": (
            f"AI analysis is temporarily unavailable ({error_reason}). "
            f"Based on keyword matching, the following laws may be relevant to your case. "
            f"Please consult a qualified lawyer for detailed analysis."
        ),
        "timeline": [],
        "laws": laws,
        "prosecution": {
            "main_argument": "Analysis unavailable — LLM service timeout",
            "strongest_points": [],
            "burden_of_proof": "Not determined",
        },
        "defense": {
            "main_argument": "Analysis unavailable — LLM service timeout",
            "counter_points": [],
            "possible_loopholes": [],
        },
        "consequences": {
            "criminal": "Consult a lawyer for specific consequences",
            "civil": "Consult a lawyer for specific consequences",
            "bail_status": "Not determined",
        },
        "confidence_score": 0.15,
        "missing_info": [
            "Full AI analysis unavailable",
            "Results are from keyword matching only",
            "Consult a qualified lawyer",
        ],
        "disclaimer": "This analysis is AI-generated and not legal advice. Consult a qualified lawyer.",
        "_partial": True,
        "_error": error_reason,
    }
