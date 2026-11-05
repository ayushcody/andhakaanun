"""
In-memory keyword fallback for when Pinecone is unavailable.
Pre-loaded IPC/CrPC/MVA map per PRD §9.3 fallback chain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("andhakaanun.fallback")


@dataclass
class FallbackLaw:
    """Minimal law entry for in-memory fallback."""

    section_id: str
    act: str
    section_number: str
    title: str
    full_text: str
    simplified: str
    domain: str
    max_punishment: str = ""
    bailable: bool = False
    cognizable: bool = False
    keywords: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────
# Pre-loaded IPC/MVA Map (Critical sections only)
# ──────────────────────────────────────────────

FALLBACK_LAWS: dict[str, FallbackLaw] = {
    "IPC_279": FallbackLaw(
        section_id="IPC_279",
        act="IPC",
        section_number="279",
        title="Rash driving or riding on a public way",
        full_text="Whoever drives any vehicle, or rides, on any public way in a manner so rash or negligent as to endanger human life, or to be likely to cause hurt or injury to any other person, shall be punished with imprisonment of either description for a term which may extend to six months, or with fine which may extend to one thousand rupees, or with both.",
        simplified="Rash or negligent driving on public roads that endangers lives. Punishable by up to 6 months imprisonment or fine up to Rs. 1000.",
        domain="traffic_criminal",
        max_punishment="6 months imprisonment or fine up to Rs. 1000",
        bailable=True,
        cognizable=True,
        keywords=[
            "rash driving",
            "negligent driving",
            "speeding",
            "reckless driving",
            "road accident",
        ],
    ),
    "IPC_304A": FallbackLaw(
        section_id="IPC_304A",
        act="IPC",
        section_number="304A",
        title="Causing death by negligence",
        full_text="Whoever causes the death of any person by doing any rash or negligent act not amounting to culpable homicide, shall be punished with imprisonment of either description for a term which may extend to two years, or with fine, or with both.",
        simplified="Causing death through negligent actions (not intentional killing). Punishable by up to 2 years imprisonment.",
        domain="traffic_criminal",
        max_punishment="2 years imprisonment",
        bailable=True,
        cognizable=True,
        keywords=[
            "death",
            "killed",
            "negligent death",
            "accident death",
            "pedestrian killed",
            "fatal accident",
        ],
    ),
    "IPC_338": FallbackLaw(
        section_id="IPC_338",
        act="",
        section_number="338",
        title="Causing grievous hurt by act endangering life or personal safety of others",
        full_text="Whoever causes grievous hurt to any person by doing any act so rashly or negligently as to endanger human life, or the personal safety of others, shall be punished with imprisonment of either description for a term which may extend to two years, or with fine which may extend to one thousand rupees, or with both.",
        simplified="Causing serious injury through rash or negligent acts. Up to 2 years imprisonment.",
        domain="traffic_criminal",
        max_punishment="2 years imprisonment or fine up to Rs. 1000",
        bailable=True,
        cognizable=True,
        keywords=["grievous hurt", "serious injury", "injury", "accident injury"],
    ),
    "_337": FallbackLaw(
        section_id="IPC_337",
        act="IPC",
        section_number="337",
        title="Causing hurt by act endangering life or personal safety of others",
        full_text="Whoever causes hurt to any person by doing any act so rashly or negligently as to endanger human life, or the personal safety of others, shall be punished with imprisonment of either description for a term which may extend to six months, or with fine which may extend to five hundred rupees, or with both.",
        simplified="Causing hurt through rash or negligent acts. Up to 6 months imprisonment.",
        domain="traffic_criminal",
        max_punishment="6 months imprisonment or fine up to Rs. 500",
        bailable=True,
        cognizable=True,
        keywords=["hurt", "minor injury"],
    ),
    "IPC_302": FallbackLaw(
        section_id="IPC_302",
        act="IPC",
        section_number="302",
        title="Punishment for murder",
        full_text="Whoever commits murder shall be punished with death, or imprisonment for life, and shall also be liable to fine.",
        simplified="Punishment for intentional killing (murder). Death penalty or life imprisonment.",
        domain="criminal",
        max_punishment="Death or life imprisonment",
        bailable=False,
        cognizable=True,
        keywords=["murder", "killed intentionally", "homicide"],
    ),
    "IPC_307": FallbackLaw(
        section_id="IPC_307",
        act="IPC",
        section_number="307",
        title="Attempt to murder",
        full_text="Whoever does any act with such intention or knowledge, and under such circumstances that, if he by that act caused death, he would be guilty of murder, shall be punished with imprisonment of either description for a term which may extend to ten years, and shall also be liable to fine.",
        simplified="Attempting to kill someone. Up to 10 years imprisonment, or life if hurt is caused.",
        domain="criminal",
        max_punishment="10 years to life imprisonment",
        bailable=False,
        cognizable=True,
        keywords=["attempt to murder", "tried to kill", "attempted murder"],
    ),
    "IPC_351": FallbackLaw(
        section_id="IPC_351",
        act="IPC",
        section_number="351",
        title="Assault",
        full_text="Whoever makes any gesture, or any preparation intending or knowing it to be likely that such gesture or preparation will cause any person present to apprehend that he who makes that gesture or preparation is about to use criminal force to that person, is said to commit an assault.",
        simplified="Making threatening gestures or preparations to use criminal force against someone.",
        domain="criminal",
        max_punishment="3 months imprisonment or fine up to Rs. 500",
        bailable=True,
        cognizable=False,
        keywords=["assault", "attack", "threatened", "beat", "hit", "punch", "slap"],
    ),
    "IPC_378": FallbackLaw(
        section_id="IPC_378",
        act="IPC",
        section_number="378",
        title="Theft",
        full_text="Whoever, intending to take dishonestly any moveable property out of the possession of any person without that person's consent, moves that property in order to such taking, is said to commit theft.",
        simplified="Dishonestly taking someone's moveable property without consent.",
        domain="criminal",
        max_punishment="3 years imprisonment or fine",
        bailable=False,
        cognizable=True,
        keywords=["theft", "stolen", "stole", "robbery", "pickpocket", "shoplifting"],
    ),
    "IPC_420": FallbackLaw(
        section_id="IPC_420",
        act="IPC",
        section_number="420",
        title="Cheating and dishonestly inducing delivery of property",
        full_text="Whoever cheats and thereby dishonestly induces the person deceived to deliver any property to any person, or to make, alter or destroy the whole or any part of a valuable security, or anything which is signed or sealed, and which is capable of being converted into a valuable security, shall be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine.",
        simplified="Cheating someone and getting them to hand over property through deception. Up to 7 years.",
        domain="criminal",
        max_punishment="7 years imprisonment and fine",
        bailable=False,
        cognizable=True,
        keywords=["cheating", "fraud", "scam", "cheat", "deceived", "conned", "defraud"],
    ),
    "IPC_498A": FallbackLaw(
        section_id="IPC_498A",
        act="IPC",
        section_number="498A",
        title="Husband or relative of husband subjecting woman to cruelty",
        full_text="Whoever, being the husband or the relative of the husband of a woman, subjects such woman to cruelty shall be punished with imprisonment for a term which may extend to three years and shall also be liable to fine.",
        simplified="Cruelty by husband or in-laws towards a married woman (dowry harassment). Up to 3 years.",
        domain="domestic",
        max_punishment="3 years imprisonment and fine",
        bailable=False,
        cognizable=True,
        keywords=[
            "domestic violence",
            "dowry",
            "cruelty",
            "harassment",
            "wife beating",
            "marital cruelty",
        ],
    ),
    "IPC_499": FallbackLaw(
        section_id="IPC_499",
        act="IPC",
        section_number="499",
        title="Defamation",
        full_text="Whoever, by words either spoken or intended to be read, or by signs or by visible representations, makes or publishes any imputation concerning any person intending to harm, or knowing or having reason to believe that such imputation will harm, the reputation of such person, is said, except in the cases hereinafter expected, to defame that person.",
        simplified="Making or publishing statements that harm someone's reputation. Criminal defamation.",
        domain="criminal",
        max_punishment="2 years imprisonment or fine",
        bailable=True,
        cognizable=False,
        keywords=["defamation", "defamed", "reputation", "slander", "libel"],
    ),
    "IT_66": FallbackLaw(
        section_id="IT_66",
        act="IT_Act",
        section_number="66",
        title="Computer related offences",
        full_text="If any person, dishonestly or fraudulently, does any act referred to in section 43, he shall be punishable with imprisonment for a term which may extend to three years or with fine which may extend to five lakh rupees or with both.",
        simplified="Hacking or unauthorized computer access. Up to 3 years or Rs. 5 lakh fine.",
        domain="cyber",
        max_punishment="3 years imprisonment or Rs. 5 lakh fine",
        bailable=True,
        cognizable=True,
        keywords=["hacking", "hacked", "computer", "unauthorized access", "cyber attack"],
    ),
    "IT_66A": FallbackLaw(
        section_id="IT_66A",
        act="IT_Act",
        section_number="66A",
        title="Punishment for sending offensive messages (Struck down)",
        full_text="Section 66A was struck down by the Supreme Court in Shreya Singhal v. Union of India (2015) as unconstitutional. However, it is still sometimes cited in FIRs.",
        simplified="Sending offensive messages online — this section was struck down by Supreme Court in 2015 but still gets cited.",
        domain="cyber",
        max_punishment="Struck down — not applicable",
        bailable=True,
        cognizable=True,
        keywords=["cyberbullying", "online abuse", "offensive message", "social media abuse"],
    ),
    "IT_43A": FallbackLaw(
        section_id="IT_43A",
        act="IT_Act",
        section_number="43A",
        title="Compensation for failure to protect data",
        full_text="Where a body corporate, possessing, dealing or handling any sensitive personal data or information in a computer resource which it owns, controls or operates, is negligent in implementing and maintaining reasonable security practices and procedures and thereby causes wrongful loss or wrongful gain to any person, such body corporate shall be liable to pay damages by way of compensation to the person so affected.",
        simplified="Companies liable for damages if they fail to protect sensitive personal data due to negligence.",
        domain="cyber",
        max_punishment="Compensation for damages",
        bailable=True,
        cognizable=False,
        keywords=["data breach", "data leak", "personal data", "privacy violation"],
    ),
    "MVA_184": FallbackLaw(
        section_id="MVA_184",
        act="MVA",
        section_number="184",
        title="Driving dangerously",
        full_text="Whoever drives a motor vehicle at a speed or in a manner which is dangerous to the public, having regard to all the circumstances of the case including the nature, condition and use of the place where the vehicle is driven and the amount of traffic which actually is at the time or which might reasonably be expected to be in the place, shall be punishable for the first offence with imprisonment for a term which may extend to six months or with fine which may extend to one thousand rupees, or with both.",
        simplified="Dangerous driving of motor vehicles. First offence: up to 6 months or Rs. 1000 fine.",
        domain="traffic_criminal",
        max_punishment="6 months imprisonment or Rs. 1000 fine (first offence)",
        bailable=True,
        cognizable=True,
        keywords=["dangerous driving", "rash driving", "speeding", "over speed", "drunk driving"],
    ),
    "MVA_185": FallbackLaw(
        section_id="MVA_185",
        act="MVA",
        section_number="185",
        title="Driving by a drunken person or by a person under the influence of drugs",
        full_text="Whoever, while driving, or attempting to drive, a motor vehicle has, in his blood, alcohol exceeding 30 mg. per 100 ml. of blood detected in a test by a breath analyser, shall be punishable for the first offence with imprisonment for a term which may extend to six months, or with fine which may extend to two thousand rupees, or with both.",
        simplified="Driving under influence of alcohol or drugs. BAC above 30mg/100ml. Up to 6 months.",
        domain="traffic_criminal",
        max_punishment="6 months imprisonment or Rs. 2000 fine",
        bailable=True,
        cognizable=True,
        keywords=["drunk driving", "intoxicated", "drunken driving", "alcohol", "drug", "DUI"],
    ),
    "PWDVA_2005": FallbackLaw(
        section_id="PWDVA_2005",
        act="PWDVA",
        section_number="3",
        title="Protection of Women from Domestic Violence Act, 2005",
        full_text="Any act, omission or commission or conduct of the respondent shall constitute domestic violence in case it harms or injures or endangers the health, safety, life, limb or well-being, whether mental or physical, of the aggrieved person or tends to do so and includes causing physical abuse, sexual abuse, verbal and emotional abuse and economic abuse.",
        simplified="Comprehensive protection against domestic violence — covers physical, sexual, verbal, emotional, and economic abuse.",
        domain="domestic",
        max_punishment="1 year imprisonment or Rs. 20,000 fine",
        bailable=True,
        cognizable=True,
        keywords=[
            "domestic violence",
            "wife abuse",
            "husband violence",
            "physical abuse",
            "emotional abuse",
        ],
    ),
}


def keyword_search(
    case_text: str,
    domains: list[str] | None = None,
    top_k: int = 5,
) -> list[FallbackLaw]:
    """
    In-memory keyword-based fallback search.
    Used when Pinecone is unavailable (PRD §9.3).

    Args:
        case_text: The case narrative.
        domains: Optional domain filter.
        top_k: Max results to return.

    Returns:
        Matched laws sorted by keyword hit count (descending).
    """
    text_lower = case_text.lower()
    scored: list[tuple[FallbackLaw, int]] = []

    for law in FALLBACK_LAWS.values():
        # Domain filter
        if domains and law.domain not in domains:
            continue

        # Count keyword hits
        hits = sum(1 for kw in law.keywords if kw in text_lower)
        if hits > 0:
            scored.append((law, hits))

    # Sort by hit count descending
    scored.sort(key=lambda x: x[1], reverse=True)

    results = [law for law, _ in scored[:top_k]]
    logger.info(
        "Keyword fallback returned %d results (from %d candidates)",
        len(results),
        len(scored),
    )
    return results
