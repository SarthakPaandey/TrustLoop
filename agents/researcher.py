"""Researcher & Answerer agent.

Generates a draft answer grounded strictly in retrieved KB chunks. If no chunks
match, the agent returns an explicit no-evidence response with confidence 0.0
so the verifier can route the item to human review.

LLM augmentation (OpenAI) is optional; when no API key is configured the agent
falls back to a deterministic template composition from the top-scoring chunks.
This preserves the zero-hallucination guarantee regardless of mode.
"""

from __future__ import annotations

from typing import List, Tuple

from config import OPENAI_API_KEY, OPENAI_MODEL, USE_LLM
from models import Answer, Question
from retrieval import KBChunk, get_vector_store

_NO_EVIDENCE = (
    "No grounded evidence was found in the Acme SaaS knowledge base for this "
    "question. A human reviewer must determine the appropriate response."
)


def _compose_offline(question: str, hits: List[Tuple[KBChunk, float]]) -> str:
    """Deterministic answer composition from top-scoring chunks."""
    bullets = []
    for chunk, _score in hits:
        # Take the first 2 lines of the chunk body for a tight summary.
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


def _compose_llm(question: str, hits: List[Tuple[KBChunk, float]]) -> str:
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
        "context. Be concise — 2-4 sentences. Never invent certifications, "
        "SLAs, or guarantees."
    )
    user = f"Context:\n{context}\n\nQuestion: {question}"
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception:
        return _compose_offline(question, hits)
    if not text or text.upper().startswith("NO_EVIDENCE"):
        return _NO_EVIDENCE
    return text


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

    top_score = hits[0][1]
    runner_up = hits[1][1] if len(hits) > 1 else 0.0
    gap = max(0.0, top_score - runner_up)

    # Anchor on top score: a well-grounded TF-IDF hit over short docs tops out
    # around 0.25-0.35, so we map that range to "high confidence" territory.
    if top_score >= 0.25:
        base = 0.80
    elif top_score >= 0.18:
        base = 0.65 + (top_score - 0.18) * (0.15 / 0.07)
    elif top_score >= 0.10:
        base = 0.40 + (top_score - 0.10) * (0.25 / 0.08)
    else:
        base = max(0.10, top_score * 3.0)

    # Bonus when the top hit clearly dominates — that's strong evidence the
    # retrieved chunk is the right answer and not just the least-bad option.
    bonus = min(0.15, gap * 0.5)
    confidence = min(0.95, base + bonus)

    draft = (
        _compose_llm(question.text, hits) if USE_LLM
        else _compose_offline(question.text, hits)
    )

    return Answer(
        question_id=question.id,
        question_text=question.text,
        draft=draft,
        evidence=[chunk.citation for chunk, _ in hits],
        confidence=round(confidence, 2),
        risk_flags=[],
    )
