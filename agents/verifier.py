"""Compliance Verifier agent.

Two layers of deterministic safety analysis:

Layer 1 — routing heuristics (per the PRD safety matrix). Triggers route to
human review. Heuristics intentionally inspect both the question and the draft:
a question about HIPAA must still escalate even if the answer politely declined
to make claims — the topic itself is sensitive enough to require sign-off.
Certification mentions that occur ONLY inside an explicitly negative draft
sentence ("Acme SaaS is NOT HIPAA certified") are treated as grounded negatives
and do not escalate — otherwise every answer quoting the certifications-not-held
policy would falsely route (the SOC 2 false-positive bug).

Layer 2 — claim-level grounding audit. Each factual sentence in an unanchored
draft (LLM-composed answers carry no verbatim source markers) must share
content-word overlap with the cited evidence retrieved from the knowledge base.
Sentences whose content cannot be traced to any cited chunk raise
[UNSUPPORTED_CLAIM] — the safe failure mode is always human review.
"""

from __future__ import annotations

import re

from config import CONFIDENCE_THRESHOLD
from models import Answer, Question
from retrieval import find_chunk_by_citation, tokenize

# ---- Pattern catalogue ----

# Mentions of certifications Acme SaaS does NOT hold or that warrant scrutiny.
_CERT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bhipaa\b", re.IGNORECASE),
     "[CERT_WARNING] Acme SaaS does not hold HIPAA certification."),
    (re.compile(r"\bpci[- ]?dss\b", re.IGNORECASE),
     "[CERT_WARNING] Acme SaaS is not PCI-DSS certified."),
    (re.compile(r"\bfedramp\b", re.IGNORECASE),
     "[CERT_WARNING] Acme SaaS is not FedRAMP authorized."),
    (re.compile(r"\birap\b", re.IGNORECASE),
     "[CERT_WARNING] Acme SaaS is not IRAP certified."),
    (re.compile(r"\b(csa star|csa star level)\b", re.IGNORECASE),
     "[CERT_WARNING] Acme SaaS CSA STAR status not confirmed."),
    (re.compile(r"\b(c5|bsi c5)\b", re.IGNORECASE),
     "[CERT_WARNING] Acme SaaS BSI C5 attestation not confirmed."),
)

_NEGATIVE_CUE = re.compile(
    r"\b(not|does not|do not|don't|cannot|can't|never|no)\b"
    r"|\bnot\s+currently\b|\bisn't\b|\bwasn't\b|\baren't\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Absolute legal language that must be softened by a human.
_LEGAL_ABSOLUTES = re.compile(
    r"\b(guarantee[ds]?|always safe|zero breach(es)?|never (fail|leak|breach)|"
    r"100%\s*(secure|safe|uptime)|fully compliant|unbreakable|impenetrable|"
    r"absolute(ly)?\s+(secure|safe)|no (data )?loss ever)\b",
    re.IGNORECASE,
)

# Geographic / residency questions — always escalate, contractual implications.
_GEO_TRIGGERS = re.compile(
    r"\b(where\s+is\s+.+\s+stored|data\s+residenc|geographic|"
    r"which\s+region|where\s+do\s+you\s+store|data\s+localization|"
    r"country\s+of\s+storage|data\s+center\s+location|"
    r"physical\s+location|which\s+country|data\s+sovereignty)\b",
    re.IGNORECASE,
)

# Insurance-specific patterns that need legal review.
_INSURANCE_PATTERNS = re.compile(
    r"\b(insurance|liability|indemnif|coverage|policy\s+limit)\b",
    re.IGNORECASE,
)


def _sentence_is_negative(sentence: str) -> bool:
    return bool(_NEGATIVE_CUE.search(sentence))


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _check_certifications(answer: Answer, question: Question) -> list[str]:
    """Negation-aware certification escalation.

    - Cert named in the QUESTION -> always escalate (sensitive topic rule).
    - Cert found ONLY in the DRAFT -> escalate unless every sentence naming it
      is explicitly negative (grounded negative from the not-held policy doc).
    """
    flags: list[str] = []
    for pattern, flag in _CERT_PATTERNS:
        in_question = bool(pattern.search(question.text))
        in_draft = bool(pattern.search(answer.draft))
        if in_question:
            flags.append(flag)
            continue
        if not in_draft:
            continue
        sentences_naming = [
            s for s in _sentences(answer.draft) if pattern.search(s)
        ]
        if any(not _sentence_is_negative(s) for s in sentences_naming):
            flags.append(flag)
    return flags


def _resolve_evidence_text(answer: Answer) -> str | None:
    """Concatenate the KB text behind each citation.

    Returns None when no citation resolves to an indexed chunk (synthetic or
    external references) — the audit then stays silent instead of guessing.
    """
    texts: list[str] = []
    for cite in answer.evidence:
        chunk = find_chunk_by_citation(cite)
        if chunk is not None:
            texts.append(chunk.text)
    return "\n".join(texts) if texts else None


def _unsupported_claims(answer: Answer) -> list[str]:
    """Flag draft sentences whose content words never appear in the evidence.

    Only runs on 'unanchored' drafts — offline composition embeds verbatim
    '(source: ...)' markers and is grounded by construction; the standard
    no-evidence response carries no factual claims. Requires at least one
    citation to resolve against the live index, so hand-built Answers with
    synthetic citations are never falsely accused.
    """
    draft = answer.draft.strip()
    if not draft or not answer.evidence:
        return []
    if "(source:" in draft:
        return []  # anchored template output — grounded by construction
    lowered = draft.lower()
    if lowered.startswith("no grounded evidence"):
        return []

    evidence_text = _resolve_evidence_text(answer)
    if evidence_text is None:
        return []
    evidence_tokens = set(tokenize(evidence_text))

    unsupported: list[str] = []
    for sentence in _sentences(draft):
        tokens = tokenize(sentence)
        # Skip short/structural sentences that cannot be meaningfully judged.
        if len(tokens) < 4:
            continue
        overlap = sum(1 for t in set(tokens) if t in evidence_tokens)
        ratio = overlap / len(set(tokens))
        if ratio < 0.5 and overlap < 3:
            snippet = sentence if len(sentence) <= 120 else sentence[:117] + "..."
            unsupported.append(snippet)
    return unsupported


def _check_claim_grounding(answer: Answer) -> list[str]:
    snippets = _unsupported_claims(answer)
    if not snippets:
        return []
    preview = " | ".join(snippets[:3])
    return [
        (
            f"[UNSUPPORTED_CLAIM] {len(snippets)} sentence(s) could not be traced "
            f"to cited evidence: {preview}"
        )
    ]


def _check_legal_absolutes(answer: Answer, question: Question) -> list[str]:
    combined = f"{question.text}\n{answer.draft}"
    if _LEGAL_ABSOLUTES.search(combined):
        return [
            "[LEGAL_RISK] Absolute guarantees found in text. Requires phrasing edit."
        ]
    return []


def _check_geography(answer: Answer, question: Question) -> list[str]:
    if _GEO_TRIGGERS.search(question.text):
        return [
            "[DATA_RESIDENCY] Geographic storage question requires reviewer sign-off."
        ]
    return []


def _check_evidence(answer: Answer) -> list[str]:
    if not answer.evidence:
        return [
            "[MISSING_EVIDENCE] No grounded sources found in Acme SaaS documents."
        ]
    return []


def _check_confidence(answer: Answer) -> list[str]:
    if answer.confidence < CONFIDENCE_THRESHOLD:
        return [
            (
                f"[LOW_CONFIDENCE] Answer confidence score "
                f"({answer.confidence:.2f}) is below threshold ({CONFIDENCE_THRESHOLD})."
            )
        ]
    return []


def _check_legal_category(question: Question) -> list[str]:
    if question.category == "legal":
        return ["[ROUTING] All legal items require review by default."]
    return []


def _check_insurance(answer: Answer, question: Question) -> list[str]:
    """Flag insurance-related answers for legal review."""
    if _INSURANCE_PATTERNS.search(question.text):
        return ["[ROUTING] Insurance-related questions require legal review."]
    return []


def verify_answer(answer: Answer, question: Question) -> Answer:
    """Run both verification layers and return an updated Answer."""
    flags: list[str] = []
    flags.extend(_check_evidence(answer))
    flags.extend(_check_certifications(answer, question))
    flags.extend(_check_legal_absolutes(answer, question))
    flags.extend(_check_geography(answer, question))
    flags.extend(_check_legal_category(question))
    flags.extend(_check_insurance(answer, question))
    flags.extend(_check_claim_grounding(answer))
    flags.extend(_check_confidence(answer))

    # Deduplicate while preserving order.
    seen = set()
    ordered_flags: list[str] = []
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
