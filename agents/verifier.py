"""Compliance Verifier agent.

Runs deterministic safety heuristics against a drafted answer + originating
question. Triggers route to human review per the safety matrix in the PRD.

Heuristics intentionally inspect both the question and the draft. A question
about HIPAA must still escalate even if the LLM answer politely declined to
make claims — the topic itself is sensitive enough to require human sign-off.
"""

from __future__ import annotations

import re
from typing import List

from config import CONFIDENCE_THRESHOLD
from models import Answer, Question

# ---- Pattern catalogue ----

# Mentions of certifications Acme SaaS does NOT hold or that warrant scrutiny.
_CERT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bhipaa\b", re.I),
     "[CERT_WARNING] Acme SaaS does not hold HIPAA certification."),
    (re.compile(r"\bpci[- ]?dss\b", re.I),
     "[CERT_WARNING] Acme SaaS is not PCI-DSS certified."),
    (re.compile(r"\bfedramp\b", re.I),
     "[CERT_WARNING] Acme SaaS is not FedRAMP authorized."),
    (re.compile(r"\birap\b", re.I),
     "[CERT_WARNING] Acme SaaS is not IRAP certified."),
)

# Absolute legal language that must be softened by a human.
_LEGAL_ABSOLUTES = re.compile(
    r"\b(guarantee[ds]?|always safe|zero breach(es)?|never (fail|leak|breach)|"
    r"100%\s*(secure|safe|uptime)|fully compliant)\b",
    re.I,
)

# Geographic / residency questions — always escalate, contractual implications.
_GEO_TRIGGERS = re.compile(
    r"\b(where\s+is\s+.+\s+stored|data\s+residenc|geographic|"
    r"which\s+region|where\s+do\s+you\s+store|data\s+localization)\b",
    re.I,
)


def _check_certifications(answer: Answer, question: Question) -> List[str]:
    flags: List[str] = []
    combined = f"{question.text}\n{answer.draft}"
    for pattern, flag in _CERT_PATTERNS:
        if pattern.search(combined):
            flags.append(flag)
    return flags


def _check_legal_absolutes(answer: Answer, question: Question) -> List[str]:
    combined = f"{question.text}\n{answer.draft}"
    if _LEGAL_ABSOLUTES.search(combined):
        return [
            "[LEGAL_RISK] Absolute guarantees found in text. Requires phrasing edit."
        ]
    return []


def _check_geography(answer: Answer, question: Question) -> List[str]:
    if _GEO_TRIGGERS.search(question.text):
        return [
            "[DATA_RESIDENCY] Geographic storage question requires reviewer sign-off."
        ]
    return []


def _check_evidence(answer: Answer) -> List[str]:
    if not answer.evidence:
        return [
            "[MISSING_EVIDENCE] No grounded sources found in Acme SaaS documents."
        ]
    return []


def _check_confidence(answer: Answer) -> List[str]:
    if answer.confidence < CONFIDENCE_THRESHOLD:
        return [
            f"[LOW_CONFIDENCE] Answer confidence score "
            f"({answer.confidence:.2f}) is below threshold ({CONFIDENCE_THRESHOLD})."
        ]
    return []


def _check_legal_category(question: Question) -> List[str]:
    if question.category == "legal":
        return ["[ROUTING] All legal items require review by default."]
    return []


def verify_answer(answer: Answer, question: Question) -> Answer:
    """Run all heuristics and return an updated Answer with risk_flags + status."""
    flags: List[str] = []
    flags.extend(_check_evidence(answer))
    flags.extend(_check_certifications(answer, question))
    flags.extend(_check_legal_absolutes(answer, question))
    flags.extend(_check_geography(answer, question))
    flags.extend(_check_legal_category(question))
    flags.extend(_check_confidence(answer))

    # Deduplicate while preserving order.
    seen = set()
    ordered_flags: List[str] = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            ordered_flags.append(f)

    updated = answer.model_copy(update={"risk_flags": ordered_flags})
    if ordered_flags:
        updated.status = "needs_review"
    else:
        updated.status = "auto_approved"
    return updated
