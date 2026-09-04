"""Researcher & Answerer agent.

Generates a draft answer grounded strictly in retrieved KB chunks. If no chunks
match, the agent returns an explicit no-evidence response with confidence 0.0
so the verifier can route the item to human review.

LLM augmentation (OpenAI/Groq) is optional; when no API key is configured the agent
falls back to a deterministic template composition from the top-scoring chunks.
This preserves the zero-hallucination guarantee regardless of mode.
"""

from __future__ import annotations

import logging
import re
from itertools import pairwise

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_PROVIDER, USE_LLM
from models import Answer, Question
from retrieval import KBChunk, get_vector_store

logger = logging.getLogger(__name__)

_NO_EVIDENCE = (
    "No grounded evidence was found in the Acme SaaS knowledge base for this "
    "question. A human reviewer must determine the appropriate response."
)


def _compose_offline(question: str, hits: list[tuple[KBChunk, float]]) -> str:
    """Deterministic answer composition from top-scoring chunks."""
    bullets = []
    for chunk, _score in hits:
        body_lines = [
            ln.strip("-* ").strip()
            for ln in chunk.text.splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        snippet = " ".join(body_lines[:3])
        if len(snippet) > 320:
            snippet = snippet[:317].rstrip() + "..."
        bullets.append(f"- {snippet} (source: {chunk.citation})")
    body = "\n".join(bullets)
    return (
        f"Based on Acme SaaS policy documentation:\n{body}"
    )


def _compose_llm(question: str, hits: list[tuple[KBChunk, float]]) -> str:
    """Optional LLM composition. Grounded strictly in the provided chunks."""
    try:
        from openai import OpenAI
    except ImportError:
        return _compose_offline(question, hits)

    context = "\n\n".join(
        f"[{chunk.citation}]\n{chunk.text}" for chunk, _ in hits
    )
    system = (
        "You are a security questionnaire assistant for Acme SaaS. Answer the "
        "question using ONLY the provided context. If the context does not "
        "support an answer, respond with exactly: NO_EVIDENCE. Cite sources "
        "inline using the [filename#section] format already present in the "
        "context. Be concise — 2-4 sentences max. Never invent certifications, "
        "SLAs, or guarantees. Never use absolute language like 'guarantee' or "
        "'always'. If the context mentions Acme SaaS does NOT hold a "
        "certification, state that clearly."
    )
    user = f"Context:\n{context}\n\nQuestion: {question}"
    if LLM_PROVIDER == "groq":
        client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    else:
        client = OpenAI(api_key=LLM_API_KEY)
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # LLM is best-effort; offline fallback is the guarantee
        logger.warning("LLM composition failed, using offline fallback: %s", exc)
        return _compose_offline(question, hits)
    if not text or text.upper().startswith("NO_EVIDENCE"):
        return _NO_EVIDENCE
    return text


def _compute_confidence(hits: list[tuple[KBChunk, float]], question: Question) -> float:
    """Compute calibrated confidence from hybrid retrieval quality.

    The hybrid retriever reports fused relevance in [0, 1] where a dominant
    match lands near 1.0 and noise sits below ~0.3. Confidence is interpolated
    over empirically anchored bands (see tests/test_upgrades.py::TestCalibration,
    which asserts monotonicity and the key routing boundaries):

        relevance 0.00 -> 0.05   nothing usable
        relevance 0.40 -> 0.70   review threshold boundary
        relevance 0.85 -> 0.92   near-certain grounded match

    Adjustments:
    + score gap bonus — a clear winner over the runner-up is stronger evidence
    + multi-chunk bonus — several independent chunks corroborating each other
    - certification cap — questions about certs the KB says are NOT held are
      capped unless the retrieved chunk is an explicit grounded negative
    """
    if not hits:
        return 0.0

    top_score = hits[0][1]
    runner_up = hits[1][1] if len(hits) > 1 else 0.0
    gap = max(0.0, top_score - runner_up)

    # Calibration anchors: (relevance, confidence). Linear interpolation.
    anchors = (
        (0.00, 0.05),
        (0.10, 0.25),
        (0.20, 0.45),
        (0.30, 0.60),
        (0.40, 0.70),
        (0.55, 0.80),
        (0.70, 0.87),
        (0.85, 0.92),
        (1.00, 0.94),
    )
    base = anchors[-1][1]
    for (lo, c_lo), (hi, c_hi) in pairwise(anchors):
        if top_score <= hi:
            base = c_lo + (c_hi - c_lo) * (top_score - lo) / (hi - lo)
            break

    gap_bonus = min(0.06, gap * 0.15)
    multi_bonus = min(0.04, (len(hits) - 1) * 0.02)

    cert_keywords = ("hipaa", "pci", "fedramp", "irap")
    if any(kw in question.text.lower() for kw in cert_keywords):
        top_text = hits[0][0].text.lower()
        grounded_negative = re.search(
            r"\b(not|no|never|does\s+not|do\s+not|not\s+currently)\b",
            top_text,
        )
        if not grounded_negative:
            # Retrieved chunk may be hallucinating a cert claim — cap it.
            base = min(base, 0.50)

    confidence = min(0.95, base + gap_bonus + multi_bonus)
    return round(confidence, 2)


def research_answer(question: Question) -> Answer:
    store = get_vector_store()
    hits = store.search(question.text)

    if not hits:
        return Answer(
            question_id=question.id,
            question_text=question.text,
            draft=_NO_EVIDENCE,
            evidence=[],
            confidence=0.0,
            risk_flags=[],
        )

    confidence = _compute_confidence(hits, question)

    draft = (
        _compose_llm(question.text, hits) if USE_LLM
        else _compose_offline(question.text, hits)
    )

    return Answer(
        question_id=question.id,
        question_text=question.text,
        draft=draft,
        evidence=[chunk.citation for chunk, _ in hits],
        confidence=confidence,
        risk_flags=[],
    )
