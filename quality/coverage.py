"""Point at questions the knowledge base does not actually answer.

Missing evidence is already a review flag. This report tells the security
owner which policy to write so the next run can ground the answer instead of
sending it back to a human.
"""

from __future__ import annotations

import re

from models import Answer
from quality.triage import flag_codes

_SUGGESTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bhipaa\b|\bphi\b", re.IGNORECASE),
        "Add a short policy that states whether you sign BAAs or store PHI.",
    ),
    (
        re.compile(r"\bpci\b", re.IGNORECASE),
        "Add a PCI scope statement, including whether card data touches your systems.",
    ),
    (
        re.compile(r"\bfedramp\b|\birap\b", re.IGNORECASE),
        "Add an authorization-status note for government frameworks you do not hold.",
    ),
    (
        re.compile(r"residenc|where .{0,30}stored|which region", re.IGNORECASE),
        "Add a data-residency policy with primary regions and any regional add-ons.",
    ),
    (
        re.compile(r"indemn|insurance|\bsla\b|guarantee", re.IGNORECASE),
        "Add the contractual source (MSA, SLA, or insurance summary) this answer should cite.",
    ),
    (
        re.compile(r"encrypt", re.IGNORECASE),
        "Add or extend the encryption policy so this control is stated directly.",
    ),
)

_DEFAULT_SUGGESTION = (
    "Add a knowledge-base document that answers this question in the customer's words."
)


def _suggestion(question: str) -> str:
    for pattern, text in _SUGGESTIONS:
        if pattern.search(question):
            return text
    return _DEFAULT_SUGGESTION


def coverage_gaps(answers: list[Answer]) -> list[dict[str, object]]:
    """Questions whose draft is thin: no citation, a missing-evidence flag, or both."""
    gaps: list[dict[str, object]] = []
    for answer in answers:
        codes = set(flag_codes(answer.risk_flags))
        reasons: list[str] = []
        if "MISSING_EVIDENCE" in codes:
            reasons.append("missing_evidence")
        if not answer.evidence:
            reasons.append("no_citations")
        if not reasons:
            continue
        gaps.append(
            {
                "question_id": answer.question_id,
                "question": answer.question_text,
                "reasons": reasons,
                "confidence": answer.confidence,
                "suggestion": _suggestion(answer.question_text),
            }
        )
    return gaps
