"""Generates the prospect-facing email draft summarizing the run."""

from __future__ import annotations

from typing import List

from config import COMPANY_NAME, PROSPECT_NAME
from models import Answer

from .exporter import summarize_run


def draft_prospect_email(answers: List[Answer]) -> str:
    summary = summarize_run(answers)
    rejected_line = (
        f"\n  - {summary.rejected} item(s) require follow-up — your security "
        "team will receive a separate note."
        if summary.rejected
        else ""
    )

    body = f"""Subject: {COMPANY_NAME} Security Questionnaire — Completed Responses

Hi {PROSPECT_NAME} team,

Thanks again for sharing the security questionnaire. Our team has completed our
responses and the attached workbook contains the full set of answers with
inline source citations.

Run summary:
  - Total questions processed: {summary.total}
  - Auto-verified against policy ({summary.auto_pct:.0f}%): {summary.auto_approved}
  - Reviewed and approved by our security team: {summary.human_approved}{rejected_line}

Each response references the underlying policy document so your team can trace
every answer back to source. A signed DPA and our latest SOC 2 Type II report
are available under NDA — let me know if you'd like either kicked off.

Happy to set up a working session to walk through anything that needs more
context.

Best,
The {COMPANY_NAME} Team
"""
    return body.strip() + "\n"
