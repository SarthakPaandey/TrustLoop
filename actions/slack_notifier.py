"""Slack notification: markdown block builder + optional real webhook delivery.

``build_slack_notification`` stays fully offline (used by the UI preview and
tests). ``send_slack_notification`` posts to a real incoming webhook when one
is configured; without a URL it degrades to dry-run and never raises.
"""

from __future__ import annotations

import logging

from config import COMPANY_NAME, PROSPECT_NAME, SLACK_WEBHOOK_URL
from models import Answer

from .exporter import summarize_run

logger = logging.getLogger(__name__)


def build_slack_notification(answers: list[Answer]) -> str:
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


def send_slack_notification(
    answers: list[Answer],
    webhook_url: str | None = None,
) -> dict:
    """Deliver the notification to a Slack incoming webhook.

    Returns a dict: {"delivered": bool, "dry_run": bool, "detail": str}.
    Order of resolution for the webhook URL: explicit arg > config secret.
    Never raises — delivery failures are logged and reported in the result.
    """
    url = webhook_url or SLACK_WEBHOOK_URL
    text = build_slack_notification(answers)
    if not url:
        return {"delivered": False, "dry_run": True,
                "detail": "No SLACK_WEBHOOK_URL configured — preview only."}
    try:
        import httpx

        resp = httpx.post(url, json={"text": text}, timeout=10)
        ok = resp.status_code == 200
        return {
            "delivered": ok,
            "dry_run": False,
            "detail": f"Slack responded {resp.status_code}.",
        }
    except httpx.HTTPError as exc:
        logger.warning("slack delivery failed: %s", exc)
        return {"delivered": False, "dry_run": False, "detail": f"Delivery failed: {exc}"}
