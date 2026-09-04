"""Centralized runtime configuration for TrustLoop."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
KB_DIR = ROOT / "kb"
EXPORTS_DIR = ROOT / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.getenv("TRUSTLOOP_DB_PATH", str(DATA_DIR / "trustloop.db")))

COMPANY_NAME = "Acme SaaS"
PROSPECT_NAME = "Acme Enterprise Prospect"

# Confidence threshold below which an answer is routed to human review.
CONFIDENCE_THRESHOLD = 0.70

# Number of KB chunks returned by the retriever for any single query.
RETRIEVAL_TOP_K = 3

# Hybrid retrieval: weight of the TF-IDF signal vs the BM25 signal when fusing.
# score = TFIDF_WEIGHT * tfidf + (1 - TFIDF_WEIGHT) * bm25_relative
HYBRID_TFIDF_WEIGHT = 0.5

# Minimum fused retrieval score for a chunk to count as evidence.
RETRIEVAL_MIN_SCORE = 0.10

# Past-answer reuse: minimum similarity between a new question and a stored
# approved question before the approved answer may be reused verbatim.
ANSWER_REUSE_SIMILARITY = 0.85

# ---- Optional integrations (all degrade gracefully when unset) ----

# When set, every /api/v1/* request (except /health) must send this value in
# the X-API-Key header. Unset = open access, suitable for local dev/demo.
API_AUTH_KEY = os.getenv("TRUSTLOOP_API_KEY", "").strip()

# Incoming Slack webhook URL. When set the Slack notification can be delivered
# for real instead of only being rendered as a mockup.
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()

# Persistence master switch. SQLite survives across runs locally; on ephemeral
# hosts (Streamlit Community Cloud) the DB still works but resets on redeploy.
PERSISTENCE_ENABLED = os.getenv("TRUSTLOOP_DISABLE_DB", "").strip() not in {"1", "true", "yes"}


def _secret(key: str, default: str = "") -> str:
    """Read from env first, then Streamlit secrets (Community Cloud)."""
    import logging

    value = os.getenv(key, "").strip()
    if value:
        return value
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception as exc:  # secrets are optional; offline mode is valid
        logging.getLogger(__name__).debug("Streamlit secrets unavailable for %s: %s", key, exc)
    return default


# Optional LLM augmentation. When unset, TrustLoop runs in deterministic offline mode.
GROQ_API_KEY = _secret("GROQ_API_KEY")
GROQ_MODEL = _secret("GROQ_MODEL", "llama-3.3-70b-versatile")

OPENAI_API_KEY = _secret("OPENAI_API_KEY")
OPENAI_MODEL = _secret("OPENAI_MODEL", "gpt-4o-mini")

if GROQ_API_KEY:
    LLM_PROVIDER = "groq"
    LLM_API_KEY = GROQ_API_KEY
    LLM_MODEL = GROQ_MODEL
    LLM_BASE_URL = "https://api.groq.com/openai/v1"
    USE_LLM = True
elif OPENAI_API_KEY:
    LLM_PROVIDER = "openai"
    LLM_API_KEY = OPENAI_API_KEY
    LLM_MODEL = OPENAI_MODEL
    LLM_BASE_URL = None
    USE_LLM = True
else:
    LLM_PROVIDER = None
    LLM_API_KEY = ""
    LLM_MODEL = ""
    LLM_BASE_URL = None
    USE_LLM = False
