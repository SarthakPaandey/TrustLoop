"""Detect answers in one run that contradict each other.

A questionnaire often asks the same control twice ("encrypt at rest?" and
"is stored data encrypted?"). Auto-approval can still ship both if each draft
is grounded on its own. This check compares polarity inside a topic and only
fires when one answer affirms the control and another denies it.
"""

from __future__ import annotations

import re

from models import Answer

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]


def _polarity(text: str, positive: re.Pattern[str], negative: re.Pattern[str]) -> str:
    """Return positive, negative, mixed, or none. Negation wins inside a sentence."""
    pos = neg = False
    for sentence in _sentences(text):
        if negative.search(sentence):
            neg = True
        elif positive.search(sentence):
            pos = True
    if pos and neg:
        return "mixed"
    if pos:
        return "positive"
    if neg:
        return "negative"
    return "none"


class _Topic:
    """One control whose answers can disagree inside a single questionnaire."""

    __slots__ = ("id", "label", "negative", "positive", "scope")

    def __init__(
        self,
        id_: str,
        label: str,
        scope: re.Pattern[str],
        positive: re.Pattern[str],
        negative: re.Pattern[str],
    ) -> None:
        self.id = id_
        self.label = label
        self.scope = scope
        self.positive = positive
        self.negative = negative


# Scope is question + draft. Polarity is the draft only, so the question
# "Are you HIPAA certified?" is not itself a positive claim.
_TOPICS: tuple[_Topic, ...] = (
    _Topic(
        "encryption_at_rest",
        "Encryption at rest",
        re.compile(
            r"encrypt\w*.{0,40}at rest|at rest.{0,40}encrypt|storage encryption",
            re.IGNORECASE,
        ),
        re.compile(r"\b(aes-?256|encrypted at rest|encryption at rest)\b", re.IGNORECASE),
        re.compile(
            r"\b(not encrypted|unencrypted|do not encrypt|without encryption|"
            r"encryption is not|is not encrypted)\b",
            re.IGNORECASE,
        ),
    ),
    _Topic(
        "mfa",
        "Multi-factor authentication",
        re.compile(r"\bmfa\b|multi-factor|two-factor|\b2fa\b", re.IGNORECASE),
        re.compile(
            r"\b(required|mandatory|enforced|must use|required for all)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(not required|optional|not enforced|do not require|without mfa|"
            r"mfa is not)\b",
            re.IGNORECASE,
        ),
    ),
    _Topic(
        "hipaa",
        "HIPAA",
        re.compile(r"\bhipaa\b", re.IGNORECASE),
        re.compile(
            r"hipaa[^.\n]{0,40}\b(certified|compliant)\b|"
            r"\b(certified|compliant)\b[^.\n]{0,40}hipaa",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(not|no|n't|without)\b[^.\n]{0,40}hipaa|"
            r"hipaa[^.\n]{0,48}\b(not certified|not held|do not hold)\b",
            re.IGNORECASE,
        ),
    ),
    _Topic(
        "soc2",
        "SOC 2",
        re.compile(r"soc\s*2", re.IGNORECASE),
        re.compile(
            r"soc\s*2[^.\n]{0,48}\b(certified|type\s*ii|attested)\b|"
            r"\b(certified|maintains|holds)\b[^.\n]{0,48}soc\s*2",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(not|no|n't|without)\b[^.\n]{0,40}soc\s*2|"
            r"soc\s*2[^.\n]{0,40}\b(not certified|not held)\b",
            re.IGNORECASE,
        ),
    ),
    _Topic(
        "backups",
        "Backups",
        re.compile(r"\bbackup", re.IGNORECASE),
        re.compile(
            r"\b(daily backups|backups are (performed|taken|maintained)|"
            r"maintain backups|backups are encrypted)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(do not (maintain|perform|take) backups|no backups|backups are not)\b",
            re.IGNORECASE,
        ),
    ),
)

_RESIDENCY_SCOPE = re.compile(
    r"residenc|where.{0,30}stored|data (center|centre)|stored in",
    re.IGNORECASE,
)
_RETENTION_Q = re.compile(r"\b(retention|retained|how long)\b", re.IGNORECASE)
_DAY_COUNT = re.compile(r"\b(\d{1,4})\s+days?\b", re.IGNORECASE)


_ONLY_US = re.compile(
    r"\b(only|exclusively|solely)\b[^.\n]{0,40}\b(united states|u\.s\.a\.|usa)\b|"
    r"\b(united states|u\.s\.a\.|usa)\b[^.\n]{0,20}\b(only|exclusively|solely)\b",
    re.IGNORECASE,
)
_ONLY_EU = re.compile(
    r"\b(only|exclusively|solely)\b[^.\n]{0,40}\b(european union|eu-west|eu-central)\b|"
    r"\b(european union|eu-west|eu-central)\b[^.\n]{0,20}\b(only|exclusively|solely)\b",
    re.IGNORECASE,
)


def _exclusive_region(draft: str) -> str | None:
    """A region the draft says is the only place data lives, if exactly one is."""
    us = bool(_ONLY_US.search(draft))
    eu = bool(_ONLY_EU.search(draft))
    if us and not eu:
        return "us"
    if eu and not us:
        return "eu"
    return None


def _topic_conflicts(answers: list[Answer]) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for topic in _TOPICS:
        grouped: dict[str, list[Answer]] = {"positive": [], "negative": []}
        for answer in answers:
            blob = f"{answer.question_text}\n{answer.draft}"
            if not topic.scope.search(blob):
                continue
            pole = _polarity(answer.draft, topic.positive, topic.negative)
            if pole in grouped:
                grouped[pole].append(answer)
        for left in grouped["positive"]:
            for right in grouped["negative"]:
                found.append(
                    {
                        "topic": topic.id,
                        "label": topic.label,
                        "question_ids": [left.question_id, right.question_id],
                        "summary": (
                            f"{left.question_id} treats {topic.label} as in place, "
                            f"but {right.question_id} says it is not."
                        ),
                    }
                )
    return found


def _residency_conflicts(answers: list[Answer]) -> list[dict[str, object]]:
    exclusive: list[tuple[Answer, str]] = []
    for answer in answers:
        blob = f"{answer.question_text}\n{answer.draft}"
        if not _RESIDENCY_SCOPE.search(blob):
            continue
        region = _exclusive_region(answer.draft)
        if region:
            exclusive.append((answer, region))
    found: list[dict[str, object]] = []
    for i, (left, left_region) in enumerate(exclusive):
        for right, right_region in exclusive[i + 1 :]:
            if left_region == right_region:
                continue
            found.append(
                {
                    "topic": "data_residency",
                    "label": "Data residency",
                    "question_ids": [left.question_id, right.question_id],
                    "summary": (
                        f"{left.question_id} says data lives only in {left_region.upper()}, "
                        f"but {right.question_id} says only in {right_region.upper()}."
                    ),
                }
            )
    return found


def _retention_conflicts(answers: list[Answer]) -> list[dict[str, object]]:
    timed: list[tuple[Answer, int]] = []
    for answer in answers:
        if not _RETENTION_Q.search(answer.question_text):
            continue
        counts = [int(match) for match in _DAY_COUNT.findall(answer.draft)]
        if not counts:
            continue
        # One answer can name a deletion window and a backup window. Compare
        # the figure the customer would quote: the longest stated retention.
        timed.append((answer, max(counts)))
    found: list[dict[str, object]] = []
    for i, (left, left_days) in enumerate(timed):
        for right, right_days in timed[i + 1 :]:
            small, large = sorted((left_days, right_days))
            if small == 0 or large / small < 2:
                continue
            found.append(
                {
                    "topic": "retention",
                    "label": "Retention period",
                    "question_ids": [left.question_id, right.question_id],
                    "summary": (
                        f"{left.question_id} states {left_days} days and "
                        f"{right.question_id} states {right_days} days."
                    ),
                }
            )
    return found


def find_conflicts(answers: list[Answer]) -> list[dict[str, object]]:
    """Contradictions a reviewer should resolve before the packet is sent."""
    return _topic_conflicts(answers) + _residency_conflicts(answers) + _retention_conflicts(answers)
