"""Analytics engine: computes business metrics from stored run history.

All functions are pure — they take the flat answer rows produced by
storage.db.analytics_rows() and return JSON-friendly dicts ready for the UI
and the /api/v1/analytics endpoint. No DB access happens here, which keeps
the metric logic unit-testable in isolation.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

_FLAG_LABELS = {
    "CERT_WARNING": "Certification warning",
    "LEGAL_RISK": "Legal risk",
    "DATA_RESIDENCY": "Data residency",
    "MISSING_EVIDENCE": "Missing evidence",
    "LOW_CONFIDENCE": "Low confidence",
    "ROUTING": "Policy routing",
    "UNSUPPORTED_CLAIM": "Unsupported claim",
}


def _flag_code(flag: str) -> str:
    return flag.split("]")[0].strip("[") if flag.startswith("[") else flag


def overview(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    statuses = Counter(r["status"] for r in rows)
    auto = statuses.get("auto_approved", 0) + statuses.get("human_approved", 0)
    confidences = [r["confidence"] for r in rows if r["confidence"]]
    avg_conf = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
    edits = sum(1 for r in rows if r.get("was_edited"))
    return {
        "total_answers": total,
        "auto_approved": statuses.get("auto_approved", 0),
        "human_approved": statuses.get("human_approved", 0),
        "needs_review": statuses.get("needs_review", 0),
        "rejected": statuses.get("rejected", 0),
        "resolution_rate": round(auto / total * 100, 1) if total else 0.0,
        "avg_confidence": avg_conf,
        "edit_rate_pct": round(edits / total * 100, 1) if total else 0.0,
    }


def flag_frequency(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter = Counter()
    for r in rows:
        for flag in r.get("risk_flags", []):
            counts[_flag_code(flag)] += 1
    return [
        {
            "code": code,
            "label": _FLAG_LABELS.get(code, code.replace("_", " ").title()),
            "count": count,
        }
        for code, count in counts.most_common()
    ]


def confidence_by_category(rows: list[dict[str, Any]]) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for r in rows:
        cat = r.get("category") or infer_category(r.get("question_text", ""))
        buckets.setdefault(cat, []).append(r["confidence"])
    return {
        cat: round(sum(vals) / len(vals), 2)
        for cat, vals in sorted(buckets.items())
        if vals
    }


def auto_rate_trend(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Auto-resolution rate per run, oldest first — the trendline KPI."""
    by_run: dict[str, dict[str, int]] = {}
    created: dict[str, str] = {}
    for r in rows:
        rid = r["run_id"]
        bucket = by_run.setdefault(rid, {"total": 0, "approved": 0})
        bucket["total"] += 1
        if r["status"] in ("auto_approved", "human_approved"):
            bucket["approved"] += 1
        created.setdefault(rid, r.get("run_created_at", ""))
    out = []
    for rid in sorted(by_run, key=lambda x: created.get(x, ""), reverse=False):
        b = by_run[rid]
        out.append({
            "run_id": rid,
            "created_at": created.get(rid, ""),
            "rate_pct": round(b["approved"] / b["total"] * 100, 1) if b["total"] else 0.0,
            "total": b["total"],
        })
    return out[-20:]


def most_flagged_questions(rows: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        qid = r["question_id"]
        entry = agg.setdefault(
            qid,
            {"question": r["question_text"], "flags": 0, "statuses": Counter()},
        )
        entry["flags"] += len(r.get("risk_flags", []))
        entry["statuses"][r["status"]] += 1
    ranked = sorted(agg.items(), key=lambda kv: kv[1]["flags"], reverse=True)[:limit]
    return [
        {
            "question_id": qid,
            "question": e["question"],
            "flag_count": e["flags"],
            "seen_in_runs": sum(e["statuses"].values()),
        }
        for qid, e in ranked
        if e["flags"] > 0
    ]


def infer_category(question_text: str) -> str:
    """Fallback category inference mirroring intake heuristics for stored rows."""
    t = question_text.lower()
    table = (
        ("certification", ("soc 2", "soc2", "iso 27001", "hipaa", "pci", "fedramp", "certif")),
        ("legal", ("guarantee", "liability", "indemnif", "warrant", "dpa ", "msa")),
        ("data-privacy", ("data stored", "residency", "retention", "pii", "subprocessor", "delete")),
        ("technical", ("encrypt", "tls", "mfa", "sso", "saml", "backup", "uptime", "vulnerab")),
    )
    for cat, keywords in table:
        if any(kw in t for kw in keywords):
            return cat
    return "general"


def compute_analytics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """One-call summary consumed by the Analytics tab and API endpoint."""
    if not rows:
        return {
            "has_data": False,
            "overview": overview(rows),
            "flag_frequency": [],
            "confidence_by_category": {},
            "auto_rate_trend": [],
            "most_flagged_questions": [],
        }
    return {
        "has_data": True,
        "overview": overview(rows),
        "flag_frequency": flag_frequency(rows),
        "confidence_by_category": confidence_by_category(rows),
        "auto_rate_trend": auto_rate_trend(rows),
        "most_flagged_questions": most_flagged_questions(rows),
    }
