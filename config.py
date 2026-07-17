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

COMPANY_NAME = "Acme SaaS"
PROSPECT_NAME = "Acme Enterprise Prospect"

# Confidence threshold below which an answer is routed to human review.
CONFIDENCE_THRESHOLD = 0.70

# Number of KB chunks returned by the retriever for any single query.
RETRIEVAL_TOP_K = 3


def _secret(key: str, default: str = "") -> str:
    """Read from env first, then Streamlit secrets (Community Cloud)."""
    value = os.getenv(key, "").strip()
    if value:
        return value
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
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
