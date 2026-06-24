"""Generates the mock Slack notification block."""

from __future__ import annotations

from typing import List

from config import PROSPECT_NAME
from models import Answer

from .exporter import summarize_run


def build_slack_notification(answers: List[Answer]) -> str:
    s = summarize_run(answers)
    return (
        "🛡️ *TrustLoop Automated Security Run Complete*\n"
        f"• Deal Account: {PROSPECT_NAME}\n"
        f"• Questions Processed: {s.total}\n"
        f"• Auto-Approved (Safe): {s.auto_approved} "
        f"({s.auto_pct:.0f}%)\n"
        f"• Human-Reviewed: {s.human_approved} "
        f"({s.reviewed_pct:.0f}%)\n"
        f"• Status: Ready for Client Delivery 🚀"
    )
