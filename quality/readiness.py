"""Score whether a finished questionnaire is safe to send to a prospect.

The score is a packaging aid, not a second verifier. Open reviews, rejections,
contradictions, and leaked secrets block sending. Thin evidence is a warning:
the reviewer may already have accepted it.
"""

from __future__ import annotations

from models import Answer
from quality.consistency import find_conflicts
from quality.coverage import coverage_gaps
from quality.sensitive import scan_answers


def _deduct(count: int, each: int, cap: int) -> int:
    return min(cap, count * each)


def assess_readiness(answers: list[Answer]) -> dict[str, object]:
    """Return score, blockers, warnings, and the underlying finding lists."""
    conflicts = find_conflicts(answers)
    sensitive = scan_answers(answers)
    gaps = coverage_gaps(answers)
    open_review = [a for a in answers if a.status == "needs_review"]
    rejected = [a for a in answers if a.status == "rejected"]

    blockers: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []

    for answer in open_review:
        blockers.append(
            {
                "severity": "high",
                "code": "OPEN_REVIEW",
                "question_id": answer.question_id,
                "message": f"{answer.question_id} is still waiting for a reviewer.",
            }
        )
    for answer in rejected:
        blockers.append(
            {
                "severity": "high",
                "code": "REJECTED",
                "question_id": answer.question_id,
                "message": f"{answer.question_id} was rejected and should not ship as-is.",
            }
        )
    for conflict in conflicts:
        blockers.append(
            {
                "severity": "high",
                "code": "CONTRADICTION",
                "question_id": conflict["question_ids"][0],
                "message": conflict["summary"],
            }
        )
    for hit in sensitive:
        item = {
            "severity": hit["severity"],
            "code": "SENSITIVE",
            "question_id": hit["question_id"],
            "message": (
                f"{hit['question_id']} contains a {hit['kind'].replace('_', ' ')} "
                f"({hit['excerpt']})."
            ),
        }
        if hit["severity"] == "high":
            blockers.append(item)
        else:
            warnings.append(item)
    for gap in gaps:
        warnings.append(
            {
                "severity": "medium",
                "code": "COVERAGE",
                "question_id": gap["question_id"],
                "message": f"{gap['question_id']}: {gap['suggestion']}",
            }
        )

    high_secrets = sum(1 for hit in sensitive if hit["severity"] == "high")
    penalty = (
        _deduct(len(open_review), 8, 40)
        + _deduct(len(rejected), 15, 30)
        + _deduct(len(conflicts), 20, 40)
        + _deduct(high_secrets, 25, 50)
        + _deduct(len(warnings), 4, 16)
    )
    return {
        "score": max(0, 100 - penalty),
        "ready_to_send": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "contradictions": conflicts,
        "sensitive": sensitive,
        "coverage_gaps": gaps,
        "counts": {
            "open_review": len(open_review),
            "rejected": len(rejected),
            "contradictions": len(conflicts),
            "sensitive": len(sensitive),
            "coverage_gaps": len(gaps),
        },
    }
