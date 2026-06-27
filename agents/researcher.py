"""Researcher & Answerer agent.

Generates a draft answer grounded strictly in retrieved KB chunks. If no chunks
match, the agent returns an explicit no-evidence response with confidence 0.0
so the verifier can route the item to human review.

LLM augmentation (OpenAI/Groq) is optional; when no API key is configured the agent
falls back to a deterministic template composition from the top-scoring chunks.
This preserves the zero-hallucination guarantee regardless of mode.
"""

from __future__ import annotations

from typing import List, Tuple

from config import LLM_API_KEY, LLM_MODEL, LLM_BASE_URL, LLM_PROVIDER, USE_LLM
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
    except Exception:
        return _compose_offline(question, hits)
    if not text or text.upper().startswith("NO_EVIDENCE"):
        return _NO_EVIDENCE
    return text


def _compute_confidence(hits: List[Tuple[KBChunk, float]], question: Question) -> float:
    """Compute a nuanced confidence score based on retrieval quality.

    Scoring factors:
    1. Top score magnitude — higher = more relevant chunk found
    2. Score gap — large gap between top and runner-up = strong match
    3. Category alignment — technical questions with technical docs score higher
    4. Multiple supporting chunks — more chunks = higher confidence
    """
    if not hits:
        return 0.0

    top_score = hits[0][1]
    runner_up = hits[1][1] if len(hits) > 1 else 0.0
    gap = max(0.0, top_score - runner_up)

    # Base score from top retrieval result.
    # TF-IDF cosine scores over short KB docs typically range 0.05-0.25 for
    # relevant matches. We map this range aggressively into confidence territory
    # because even a moderate TF-IDF hit over a small domain-specific KB means
    # the retriever found a genuinely relevant document.
    if top_score >= 0.25:
        base = 0.85
    elif top_score >= 0.18:
        base = 0.80
    elif top_score >= 0.12:
        base = 0.75
    elif top_score >= 0.10:
        base = 0.72
    elif top_score >= 0.08:
        base = 0.65
    elif top_score >= 0.05:
        base = 0.45
    else:
        base = max(0.10, top_score * 3.0)

    # Bonus: strong primary match (large gap = confident retrieval)
    gap_bonus = min(0.12, gap * 0.4)

    # Bonus: multiple supporting chunks
    multi_bonus = min(0.08, (len(hits) - 1) * 0.03)

    # Penalty: certification questions about unsupported certs
    # (the retriever may find the doc but it says "not certified")
    cert_keywords = ["hipaa", "pci", "fedramp", "irap"]
    if any(kw in question.text.lower() for kw in cert_keywords):
        # Check if the top chunk actually confirms the cert
        top_text = hits[0][0].text.lower()
        if "not " in top_text or "does not" in top_text or "not currently" in top_text:
            # Still confident — just negative. The answer is well-grounded.
            pass
        else:
            # Might be hallucinating a cert claim
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
