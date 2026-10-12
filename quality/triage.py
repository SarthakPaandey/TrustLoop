"""Order the human review queue by compliance risk.

The pipeline used to hand reviewers flagged questions in questionnaire order,
so a low-confidence wording nit could sit in front of a certification claim.
This module ranks ``needs_review`` answers by the strongest guardrail on the
draft, then by confidence, then by original position so the ranking is stable.
"""

from __future__ import annotations

from models import Answer

# Higher weight is reviewed first. Weights mirror the safety matrix: a claim
# the evidence does not support, or a certification the company does not hold,
# is more dangerous to leave in a customer packet than a generic routing flag.
FLAG_WEIGHT: dict[str, int] = {
    "UNSUPPORTED_CLAIM": 100,
    "CERT_WARNING": 90,
    "LEGAL_RISK": 80,
    "DATA_RESIDENCY": 70,
    "MISSING_EVIDENCE": 50,
    "ROUTING": 40,
    "LOW_CONFIDENCE": 20,
}

_FLAG_PHRASE = {
    "UNSUPPORTED_CLAIM": "an unsupported claim",
    "CERT_WARNING": "a certification warning",
    "LEGAL_RISK": "legal-risk language",
    "DATA_RESIDENCY": "a data-residency question",
    "MISSING_EVIDENCE": "missing evidence",
    "ROUTING": "a policy-routing rule",
    "LOW_CONFIDENCE": "low confidence",
}


def flag_codes(flags: list[str]) -> list[str]:
    """Pull ``[CODE]`` identifiers out of verifier flag strings."""
    codes: list[str] = []
    for flag in flags:
        if flag.startswith("[") and "]" in flag:
            codes.append(flag[1:flag.index("]")])
        elif flag:
            codes.append(flag)
    return codes


def risk_score(answer: Answer) -> int:
    """Strongest guardrail on this answer. Uncoded flags still outrank nothing."""
    codes = flag_codes(answer.risk_flags)
    if not codes:
        return 10 if answer.status == "needs_review" else 0
    return max(FLAG_WEIGHT.get(code, 10) for code in codes)


def prioritize_review_queue(answers: list[Answer]) -> list[str]:
    """Question ids that still need review, highest risk first.

    Ties break toward the less confident draft, then the original order, so
    two certification flags do not swap places just because the file was re-read.
    """
    ranked: list[tuple[int, float, int, str]] = []
    for index, answer in enumerate(answers):
        if answer.status != "needs_review":
            continue
        ranked.append((risk_score(answer), answer.confidence, index, answer.question_id))
    ranked.sort(key=lambda row: (-row[0], row[1], row[2]))
    return [row[3] for row in ranked]


def explain_priority(answer: Answer) -> str:
    """One sentence a reviewer can show above the current draft."""
    codes = flag_codes(answer.risk_flags)
    if not codes:
        return "Medium priority — flagged for review without a specific guardrail."
    top = max(codes, key=lambda code: (FLAG_WEIGHT.get(code, 0), code))
    weight = FLAG_WEIGHT.get(top, 0)
    if weight >= 70:
        level = "High"
    elif weight >= 40:
        level = "Medium"
    else:
        level = "Low"
    phrase = _FLAG_PHRASE.get(top, top.replace("_", " ").lower())
    return f"{level} priority — this item is here because of {phrase}."
