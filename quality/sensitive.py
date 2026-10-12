"""Scan customer-facing drafts for secrets and internal-only markers.

Approved answers are what a prospect receives. A retrieved policy chunk can
accidentally carry a key, a webhook, or a "do not share" note. Scanning happens
at export time and never rewrites the stored draft unless the caller asks for
a redacted copy.
"""

from __future__ import annotations

import re

from models import Answer

# (kind, pattern, severity). High severity blocks send. Medium is a warning.
_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "high"),
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "high",
    ),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "high"),
    (
        "slack_webhook",
        re.compile(r"https://hooks\.slack\.com/services/\S+"),
        "high",
    ),
    (
        "secret_assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|client[_-]?secret|auth[_-]?token|password)\b"
            r"\s*[:=]\s*[A-Za-z0-9+/=_\-]{12,}"
        ),
        "high",
    ),
    (
        "private_ip",
        re.compile(
            r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
        ),
        "medium",
    ),
    (
        "internal_marker",
        re.compile(r"(?i)\b(?:INTERNAL ONLY|DO NOT SHARE|CONFIDENTIAL DRAFT|FIXME|TBD)\b"),
        "high",
    ),
)


def _excerpt(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 24)
    end = min(len(text), match.end() + 24)
    snippet = text[start:end].replace("\n", " ")
    return snippet.replace(match.group(0), "[REDACTED]")


def redact_text(text: str) -> str:
    """Replace every sensitive match. Safe to call on text that has none."""
    redacted = text
    for _kind, pattern, _severity in _RULES:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def scan_text(text: str) -> list[dict[str, str]]:
    """Findings for one draft. The matched secret is not returned."""
    findings: list[dict[str, str]] = []
    for kind, pattern, severity in _RULES:
        for match in pattern.finditer(text):
            findings.append(
                {
                    "kind": kind,
                    "severity": severity,
                    "excerpt": _excerpt(text, match),
                }
            )
    return findings


def scan_answers(answers: list[Answer]) -> list[dict[str, str]]:
    """Sensitive findings across the drafts that would leave the building."""
    found: list[dict[str, str]] = []
    for answer in answers:
        if answer.status == "rejected":
            continue
        for hit in scan_text(answer.draft):
            found.append({"question_id": answer.question_id, **hit})
    return found


def redact_answers(answers: list[Answer]) -> list[Answer]:
    """Copies with sensitive spans replaced. The caller's answers stay intact."""
    return [
        answer.model_copy(update={"draft": redact_text(answer.draft)})
        for answer in answers
    ]
