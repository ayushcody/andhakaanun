"""
Jurisdiction Engine — Two-pass legal domain detection.

Pass 1: Keyword map + regex pattern matching (fast, deterministic)
Pass 2: Entity extraction fallback for unmatched cases

Matches PRD §4.1 and §4.2 exactly.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("andhakaanun.jurisdiction")


# ──────────────────────────────────────────────
# Result Type
# ──────────────────────────────────────────────

@dataclass
class JurisdictionResult:
    """Result of jurisdiction detection."""
    detected_domains: list[str] = field(default_factory=list)
    matched_sections: list[str] = field(default_factory=list)
    confidence: float = 0.0
    location: str | None = None
    method: str = "none"  # "keyword" | "ner" | "combined"
    raw_matches: dict[str, list[str]] = field(default_factory=dict)


# ──────────────────────────────────────────────
# Pass 1 — Keyword Map (PRD §4.1)
# ──────────────────────────────────────────────

KEYWORD_MAP: dict[str, list[str]] = {
    # Criminal — Traffic
    "rash driving": ["IPC_279", "MVA_184"],
    "reckless driving": ["IPC_279", "MVA_184"],
    "negligent driving": ["IPC_279", "MVA_184"],
    "speeding": ["IPC_279", "MVA_184"],
    "over speed": ["IPC_279", "MVA_184"],
    "dangerous driving": ["MVA_184", "IPC_279"],
    "road accident": ["IPC_279", "IPC_304A", "MVA_184"],
    "hit and run": ["IPC_279", "IPC_304A", "IPC_338"],
    "negligent death": ["IPC_304A"],
    "death by negligence": ["IPC_304A"],
    "fatal accident": ["IPC_304A", "IPC_279"],
    "pedestrian killed": ["IPC_304A", "IPC_279"],
    "drunk driving": ["MVA_185", "IPC_279"],
    "drunken driving": ["MVA_185", "IPC_279"],
    "driving under influence": ["MVA_185"],
    "intoxicated driving": ["MVA_185"],

    # Criminal — Violence
    "murder": ["IPC_302"],
    "killed intentionally": ["IPC_302"],
    "homicide": ["IPC_302", "IPC_304A"],
    "attempt to murder": ["IPC_307"],
    "attempted murder": ["IPC_307"],
    "tried to kill": ["IPC_307"],
    "assault": ["IPC_351", "IPC_352"],
    "attack": ["IPC_351", "IPC_352"],
    "beaten": ["IPC_351", "IPC_323"],
    "beat up": ["IPC_351", "IPC_323"],
    "punched": ["IPC_351", "IPC_323"],
    "slapped": ["IPC_351", "IPC_323"],
    "stabbed": ["IPC_307", "IPC_324"],
    "grievous hurt": ["IPC_338", "IPC_325"],
    "serious injury": ["IPC_338", "IPC_325"],

    # Criminal — Property
    "theft": ["IPC_378", "IPC_379"],
    "stolen": ["IPC_378", "IPC_379"],
    "stole": ["IPC_378", "IPC_379"],
    "robbery": ["IPC_392", "IPC_378"],
    "burglary": ["IPC_445", "IPC_457"],
    "trespass": ["IPC_441", "IPC_447"],
    "pickpocket": ["IPC_378"],
    "shoplifting": ["IPC_378"],

    # Criminal — Fraud
    "cheating": ["IPC_420"],
    "fraud": ["IPC_420"],
    "scam": ["IPC_420"],
    "deceived": ["IPC_420"],
    "conned": ["IPC_420"],
    "forgery": ["IPC_463", "IPC_465"],
    "counterfeit": ["IPC_463", "IPC_489A"],
    "criminal breach of trust": ["IPC_405", "IPC_406"],
    "embezzlement": ["IPC_405", "IPC_406"],
    "misappropriation": ["IPC_403"],

    # Criminal — Defamation
    "defamation": ["IPC_499", "IPC_500"],
    "defamed": ["IPC_499", "IPC_500"],
    "slander": ["IPC_499"],
    "libel": ["IPC_499"],

    # Criminal — Kidnapping
    "kidnapping": ["IPC_359", "IPC_363"],
    "abduction": ["IPC_362", "IPC_366"],
    "kidnapped": ["IPC_359", "IPC_363"],

    # Criminal — Sexual Offences
    "rape": ["IPC_375", "IPC_376"],
    "sexual assault": ["IPC_354", "IPC_375"],
    "molestation": ["IPC_354"],
    "eve teasing": ["IPC_354", "IPC_509"],
    "outraging modesty": ["IPC_354"],
    "voyeurism": ["IPC_354C"],
    "stalking": ["IPC_354D"],

    # Cyber
    "hacking": ["IT_66", "IT_43"],
    "hacked": ["IT_66", "IT_43"],
    "data breach": ["IT_43A", "IT_72A"],
    "data leak": ["IT_43A"],
    "cyberbullying": ["IT_66A"],
    "online abuse": ["IT_66A"],
    "cyber crime": ["IT_66", "IT_43"],
    "phishing": ["IT_66", "IT_66C"],
    "identity theft": ["IT_66C"],
    "unauthorized access": ["IT_66", "IT_43"],
    "computer virus": ["IT_43"],
    "website hacked": ["IT_66", "IT_43"],
    "online fraud": ["IT_66", "IPC_420"],
    "social media abuse": ["IT_66A"],

    # Domestic
    "domestic violence": ["PWDVA_2005", "IPC_498A"],
    "dowry": ["IPC_498A", "IPC_304B"],
    "dowry harassment": ["IPC_498A"],
    "dowry death": ["IPC_304B"],
    "cruelty by husband": ["IPC_498A"],
    "wife beating": ["IPC_498A", "PWDVA_2005"],
    "marital cruelty": ["IPC_498A"],
    "domestic abuse": ["PWDVA_2005", "IPC_498A"],

    # Consumer
    "consumer complaint": ["CPA_2019"],
    "defective product": ["CPA_2019"],
    "unfair trade": ["CPA_2019"],
    "misleading advertisement": ["CPA_2019"],

    # Property / Civil
    "property dispute": ["TPA_1882"],
    "land dispute": ["TPA_1882"],
    "encroachment": ["IPC_441", "TPA_1882"],
    "illegal possession": ["TPA_1882"],
    "eviction": ["TPA_1882"],

    # Corruption
    "bribery": ["PCA_1988"],
    "corruption": ["PCA_1988"],
    "government fraud": ["PCA_1988", "IPC_420"],
}


# ──────────────────────────────────────────────
# Regex Patterns (PRD §4.1)
# ──────────────────────────────────────────────

SECTION_PATTERN = re.compile(
    r'\bsection\s+(\d+[A-Za-z]?)\b', re.IGNORECASE
)
IPC_PATTERN = re.compile(
    r'\bIPC\s+(\d+[A-Za-z]?)\b', re.IGNORECASE
)
CRPC_PATTERN = re.compile(
    r'\bCrPC\s+(\d+[A-Za-z]?)\b', re.IGNORECASE
)
IT_ACT_PATTERN = re.compile(
    r'\bIT\s+(?:Act\s+)?(?:Section\s+)?(\d+[A-Za-z]?)\b', re.IGNORECASE
)
MVA_PATTERN = re.compile(
    r'\bMVA?\s+(?:Section\s+)?(\d+[A-Za-z]?)\b', re.IGNORECASE
)

# Domain mapping from act prefix
ACT_DOMAIN_MAP: dict[str, str] = {
    "IPC": "criminal",
    "CrPC": "criminal",
    "IT": "cyber",
    "IT_Act": "cyber",
    "MVA": "traffic_criminal",
    "CPA": "consumer",
    "TPA": "property",
    "PCA": "criminal",
    "PWDVA": "domestic",
}

# Section → Domain override (some IPC sections belong to specific domains)
SECTION_DOMAIN_OVERRIDES: dict[str, str] = {
    "IPC_279": "traffic_criminal",
    "IPC_304A": "traffic_criminal",
    "IPC_337": "traffic_criminal",
    "IPC_338": "traffic_criminal",
    "IPC_498A": "domestic",
    "IPC_304B": "domestic",
    "IPC_354": "criminal",
    "IPC_375": "criminal",
    "IPC_376": "criminal",
}


# ──────────────────────────────────────────────
# Confidence Scoring (PRD §4.2)
# ──────────────────────────────────────────────

def compute_input_confidence(
    case_text: str,
    matched_sections: list[str],
    keyword_match_count: int,
    retrieval_scores: list[float] | None = None,
) -> float:
    """
    Pre-LLM confidence scoring per PRD §4.2.

    Factors:
      1. Input length (more context = higher confidence) — weight 0.3
      2. Average retrieval similarity score — weight 0.4
      3. Keyword match count — weight 0.2
      4. Penalty for vague inputs — -0.15
    """
    score = 0.0

    # Factor 1: Input length (capped at 0.3)
    word_count = len(case_text.split())
    score += min(word_count / 100, 0.3)

    # Factor 2: Average retrieval similarity (weight 0.4)
    if retrieval_scores:
        avg_sim = sum(retrieval_scores) / len(retrieval_scores)
        score += avg_sim * 0.4
    elif matched_sections:
        # If no retrieval scores, use keyword confidence
        score += min(len(matched_sections) / 5, 0.3)

    # Factor 3: Keyword match count (weight 0.2)
    score += min(keyword_match_count / 5, 0.2)

    # Factor 4: Penalty for vague inputs
    if word_count < 30:
        score -= 0.15

    # Additional bonus for explicit section references
    if matched_sections:
        score += min(len(matched_sections) * 0.02, 0.1)

    return round(min(max(score, 0.0), 1.0), 2)


# ──────────────────────────────────────────────
# Pass 1: Keyword + Regex Matching
# ──────────────────────────────────────────────

def _keyword_pass(case_text: str) -> tuple[set[str], set[str], int, dict[str, list[str]]]:
    """
    Deterministic keyword and regex-based detection.

    Returns:
        (matched_sections, detected_domains, match_count, raw_matches)
    """
    text_lower = case_text.lower()
    matched_sections: set[str] = set()
    detected_domains: set[str] = set()
    match_count = 0
    raw_matches: dict[str, list[str]] = {}

    # --- Keyword map matching ---
    for keyword, sections in KEYWORD_MAP.items():
        if keyword in text_lower:
            match_count += 1
            raw_matches[keyword] = sections
            for section in sections:
                matched_sections.add(section)
                # Determine domain
                domain = SECTION_DOMAIN_OVERRIDES.get(section)
                if not domain:
                    act_prefix = section.split("_")[0]
                    domain = ACT_DOMAIN_MAP.get(act_prefix, "criminal")
                detected_domains.add(domain)

    # --- Regex: explicit section references ---
    for match in IPC_PATTERN.finditer(case_text):
        section_num = match.group(1)
        section_id = f"IPC_{section_num}"
        matched_sections.add(section_id)
        match_count += 1
        domain = SECTION_DOMAIN_OVERRIDES.get(section_id, "criminal")
        detected_domains.add(domain)
        raw_matches[f"IPC {section_num}"] = [section_id]

    for match in CRPC_PATTERN.finditer(case_text):
        section_num = match.group(1)
        section_id = f"CrPC_{section_num}"
        matched_sections.add(section_id)
        match_count += 1
        detected_domains.add("criminal")
        raw_matches[f"CrPC {section_num}"] = [section_id]

    for match in MVA_PATTERN.finditer(case_text):
        section_num = match.group(1)
        section_id = f"MVA_{section_num}"
        matched_sections.add(section_id)
        match_count += 1
        detected_domains.add("traffic_criminal")
        raw_matches[f"MVA {section_num}"] = [section_id]

    # --- Regex: generic "section X" references ---
    for match in SECTION_PATTERN.finditer(case_text):
        section_num = match.group(1)
        # Try to infer act from context around the match
        start = max(0, match.start() - 30)
        context = case_text[start:match.start()].lower()
        if "ipc" in context or "penal" in context:
            section_id = f"IPC_{section_num}"
            matched_sections.add(section_id)
            domain = SECTION_DOMAIN_OVERRIDES.get(section_id, "criminal")
            detected_domains.add(domain)
        elif "crpc" in context or "criminal procedure" in context:
            section_id = f"CrPC_{section_num}"
            matched_sections.add(section_id)
            detected_domains.add("criminal")
        elif "motor" in context or "mva" in context or "vehicle" in context:
            section_id = f"MVA_{section_num}"
            matched_sections.add(section_id)
            detected_domains.add("traffic_criminal")

    return matched_sections, detected_domains, match_count, raw_matches


# ──────────────────────────────────────────────
# Pass 2: Entity Extraction Fallback
# ──────────────────────────────────────────────

# Entity keywords for domain classification when no keyword matches
ENTITY_DOMAIN_SIGNALS: dict[str, list[str]] = {
    "traffic_criminal": [
        "vehicle", "car", "truck", "bus", "bike", "motorcycle", "auto",
        "road", "highway", "street", "intersection", "signal", "traffic",
        "driver", "pedestrian", "accident", "collision", "crash", "speed",
    ],
    "cyber": [
        "computer", "laptop", "phone", "mobile", "internet", "online",
        "website", "email", "password", "account", "social media",
        "facebook", "instagram", "whatsapp", "twitter", "youtube",
        "software", "app", "data", "server", "network",
    ],
    "domestic": [
        "husband", "wife", "marriage", "married", "in-laws", "mother-in-law",
        "father-in-law", "matrimonial", "divorce", "dowry", "alimony",
        "domestic", "family",
    ],
    "consumer": [
        "product", "service", "warranty", "refund", "defective",
        "customer", "company", "brand", "purchase", "bought", "paid",
        "e-commerce", "delivery", "seller", "manufacturer",
    ],
    "property": [
        "property", "land", "house", "flat", "apartment", "building",
        "tenant", "landlord", "rent", "lease", "deed", "registry",
        "encroachment", "possession", "boundary", "plot",
    ],
    "criminal": [
        "police", "fir", "complaint", "arrested", "jail", "bail",
        "court", "magistrate", "judge", "lawyer", "advocate",
        "prison", "custody", "charge sheet",
    ],
}


def _entity_fallback(case_text: str) -> tuple[set[str], int]:
    """
    Simple entity-based domain detection for unmatched cases.
    Uses keyword signals instead of spaCy NER for reliability.

    Returns:
        (detected_domains, signal_count)
    """
    text_lower = case_text.lower()
    domain_scores: dict[str, int] = {}

    for domain, signals in ENTITY_DOMAIN_SIGNALS.items():
        count = sum(1 for signal in signals if signal in text_lower)
        if count > 0:
            domain_scores[domain] = count

    if not domain_scores:
        return set(), 0

    # Return domains sorted by signal count, keep top 2
    sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
    top_domains = {d for d, _ in sorted_domains[:2]}
    total_signals = sum(c for _, c in sorted_domains[:2])

    return top_domains, total_signals


# ──────────────────────────────────────────────
# Main Detection Function
# ──────────────────────────────────────────────

async def detect_jurisdiction(
    case_text: str,
    location: str = "",
    retrieval_scores: list[float] | None = None,
) -> JurisdictionResult:
    """
    Two-pass jurisdiction detection per PRD §4.1.

    Pass 1: Keyword map + regex (fast, deterministic)
    Pass 2: Entity signal fallback (for unmatched cases)

    Args:
        case_text: The full case narrative.
        location: Optional location/state.
        retrieval_scores: Optional similarity scores from RAG retrieval.

    Returns:
        JurisdictionResult with domains, sections, and confidence.
    """
    # --- Pass 1: Keyword + Regex ---
    matched_sections, detected_domains, match_count, raw_matches = _keyword_pass(
        case_text
    )

    method = "keyword"

    # --- Pass 2: Entity fallback (if Pass 1 found nothing) ---
    if not detected_domains:
        logger.info("Pass 1 found no matches — running entity fallback")
        fallback_domains, signal_count = _entity_fallback(case_text)
        detected_domains = fallback_domains
        match_count += signal_count
        method = "ner" if fallback_domains else "none"
    elif not matched_sections:
        # Domains detected but no specific sections
        fallback_domains, signal_count = _entity_fallback(case_text)
        detected_domains |= fallback_domains
        match_count += signal_count
        method = "combined"

    # --- Confidence scoring ---
    confidence = compute_input_confidence(
        case_text=case_text,
        matched_sections=list(matched_sections),
        keyword_match_count=match_count,
        retrieval_scores=retrieval_scores,
    )

    result = JurisdictionResult(
        detected_domains=sorted(detected_domains),
        matched_sections=sorted(matched_sections),
        confidence=confidence,
        location=location or None,
        method=method,
        raw_matches=raw_matches,
    )

    logger.info(
        "Jurisdiction detected: domains=%s, sections=%d, confidence=%.2f, method=%s",
        result.detected_domains,
        len(result.matched_sections),
        result.confidence,
        result.method,
    )

    return result


# ──────────────────────────────────────────────
# Quick-detect for live typing (frontend badges)
# ──────────────────────────────────────────────

def quick_detect(text: str) -> list[dict[str, str]]:
    """
    Fast synchronous detection for real-time UI badges.
    Returns matched sections with labels.

    Used by the frontend to show "IPC 279 likely" as user types.
    """
    matched_sections, _, _, _ = _keyword_pass(text)

    badges = []
    seen = set()
    for section_id in sorted(matched_sections):
        parts = section_id.split("_")
        if len(parts) == 2:
            label = f"{parts[0]} {parts[1]}"
            if label not in seen:
                badges.append({"section": section_id, "label": label})
                seen.add(label)

    return badges[:6]  # Limit to 6 badges for UI
