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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
USE_LLM = bool(OPENAI_API_KEY)
