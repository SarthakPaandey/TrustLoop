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

# Optional LLM augmentation. When unset, TrustLoop runs in deterministic offline mode.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

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
