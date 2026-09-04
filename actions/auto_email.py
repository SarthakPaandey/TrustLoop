"""Auto-email sender for TrustLoop.

When all items are resolved and the overall confidence is high enough,
automatically sends the completed questionnaire to the prospect.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from actions.exporter import summarize_run
from config import COMPANY_NAME
from models import Answer

logger = logging.getLogger(__name__)

# Auto-send threshold: average confidence must be above this to auto-send
AUTO_SEND_CONFIDENCE_THRESHOLD = 0.70


def _compute_avg_confidence(answers: list[Answer]) -> float:
    """Compute the average confidence across all answers."""
    if not answers:
        return 0.0
    return sum(a.confidence for a in answers) / len(answers)


def _should_auto_send(answers: list[Answer]) -> tuple[bool, str]:
    """Determine if we should auto-send the email.
    
    Returns (should_send, reason).
    """
    if not answers:
        return False, "No answers to send"
    
    summary = summarize_run(answers)
    
    # Must have no items still in review or rejected
    if summary.needs_review > 0:
        return False, f"{summary.needs_review} items still need review"
    
    if summary.rejected > 0:
        return False, f"{summary.rejected} items were rejected"
    
    # Must have at least some approved answers
    if summary.human_approved + summary.auto_approved == 0:
        return False, "No approved answers"
    
    # Check average confidence
    avg_conf = _compute_avg_confidence(answers)
    if avg_conf < AUTO_SEND_CONFIDENCE_THRESHOLD:
        return False, f"Average confidence {avg_conf:.1%} is below threshold {AUTO_SEND_CONFIDENCE_THRESHOLD:.0%}"
    
    return True, f"Average confidence {avg_conf:.1%} meets threshold"


def _smtp_settings(recipient_override: str | None) -> tuple[dict, str | None]:
    """Resolve SMTP settings from env. Returns (settings, error_reason)."""
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        return {}, "Invalid SMTP_PORT — must be a number."
    settings = {
        "host": os.getenv("SMTP_HOST", ""),
        "port": smtp_port,
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASS", ""),
        "from_email": os.getenv(
            "FROM_EMAIL", f"trustloop@{COMPANY_NAME.lower().replace(' ', '')}.com"
        ),
        "to_email": recipient_override
        or os.getenv("PROSPECT_EMAIL", "security@acme-prospect.com"),
    }
    if "@" not in settings["to_email"]:
        return {}, f"Invalid recipient email: {settings['to_email']!r}."
    if not all([settings["host"], settings["user"], settings["password"]]):
        return {}, "SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASS in .env"
    return settings, None


def send_prospect_email(
    answers: list[Answer],
    recipient_email: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Send the completed questionnaire to the prospect via email.

    Args:
        answers: List of all resolved answers
        recipient_email: Override recipient (default: security@prospect.com)
        dry_run: If True, just generate the email without sending

    Returns:
        dict with status, message, and email details
    """
    from actions.email_drafter import draft_prospect_email

    should_send, reason = _should_auto_send(answers)

    if not should_send:
        return {
            "sent": False,
            "reason": reason,
            "email": None,
        }

    # Generate the email
    email_body = draft_prospect_email(answers)

    if dry_run:
        return {
            "sent": False,
            "reason": f"Dry run — would send. {reason}",
            "email": email_body,
            "avg_confidence": _compute_avg_confidence(answers),
            "total_questions": len(answers),
        }

    settings, error = _smtp_settings(recipient_email)
    if error:
        return {"sent": False, "reason": error, "email": email_body}
    smtp_host = settings["host"]
    smtp_port = settings["port"]
    smtp_user = settings["user"]
    smtp_pass = settings["password"]
    from_email = settings["from_email"]
    to_email = settings["to_email"]

    try:
        msg = MIMEMultipart()
        msg["From"] = f"{COMPANY_NAME} Security Team <{from_email}>"
        msg["To"] = to_email
        msg["Subject"] = f"{COMPANY_NAME} Security Questionnaire — Completed Responses"
        msg.attach(MIMEText(email_body, "plain"))
        
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        
        return {
            "sent": True,
            "reason": f"Email sent to {to_email}. {reason}",
            "email": email_body,
            "to": to_email,
        }
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("prospect email delivery failed: %s", exc)
        return {
            "sent": False,
            "reason": f"Failed to send: {exc!s}",
            "email": email_body,
        }


def get_email_preview(answers: list[Answer]) -> str:
    """Get the email preview without any sending logic."""
    from actions.email_drafter import draft_prospect_email
    return draft_prospect_email(answers)
