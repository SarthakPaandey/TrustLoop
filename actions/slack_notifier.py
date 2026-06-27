"""Generates the mock Slack notification block."""

from __future__ import annotations

from typing import List

from config import COMPANY_NAME, PROSPECT_NAME
from models import Answer

from .exporter import summarize_run


def build_slack_notification(answers: List[Answer]) -> str:
    s = summarize_run(answers)
    
    # Count unique sources
    all_sources = set()
    for a in answers:
        all_sources.update(a.evidence)
    
    status_emoji = "✅" if s.rejected == 0 else "⚠️"
    status_text = "Ready for Client Delivery" if s.rejected == 0 else f"{s.rejected} item(s) need attention"
    
    return (
        f"🛡️ *{COMPANY_NAME} — TrustLoop Security Run Complete*\n"
        f"\n"
        f"📋 *Deal Account:* {PROSPECT_NAME}\n"
        f"📊 *Questions Processed:* {s.total}\n"
        f"✅ *Auto-Approved (Safe):* {s.auto_approved} ({s.auto_pct:.0f}%)\n"
        f"👤 *Human-Reviewed:* {s.human_approved} ({s.reviewed_pct:.0f}%)\n"
        f"📄 *Sources Referenced:* {len(all_sources)} policy documents\n"
        f"\n"
        f"{status_emoji} *Status:* {status_text} 🚀\n"
        f"\n"
        f"_Workflow: Intake → RAG Retrieval → Compliance Verification → Human Review → Export_"
    )
