"""Persistence layer: SQLite-backed run history, decisions, and audit trail.

Design goals:
- Zero external dependencies (stdlib sqlite3), safe under Streamlit's threading.
- Every mutation appends an immutable audit_events row — who did what, when.
- All public functions degrade gracefully (log + safe default) so a storage
  failure can never crash the pipeline or the UI mid-demo.

The DB path comes from config.DB_PATH (override with TRUSTLOOP_DB_PATH, used
by tests to isolate fixtures).
"""

from __future__ import annotations

import contextvars
import csv
import json
import logging
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import DB_PATH, PERSISTENCE_ENABLED

logger = logging.getLogger(__name__)

_lock = threading.RLock()  # reentrant: writers compose (e.g. create_run -> add_event)
_local = threading.local()
# Request-scoped opt-out (ContextVar: async-safe, unlike the old global bool
# which leaked across concurrent FastAPI requests sharing the process).
_disabled_override: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "trustloop_db_disabled", default=False
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'processing',
    total_questions INTEGER NOT NULL DEFAULT 0,
    source_preview TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS answers (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    question_id TEXT NOT NULL,
    question_text TEXT NOT NULL,
    original_draft TEXT NOT NULL DEFAULT '',
    final_answer TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.0,
    risk_flags TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'needs_review',
    decided_by TEXT NOT NULL DEFAULT 'system',
    decided_at TEXT,
    was_edited INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, question_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    run_id TEXT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    question_id TEXT,
    details TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_answers_run ON answers(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_events(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def _ensure_schema() -> None:
    conn = _connect()
    conn.executescript(_SCHEMA)
    conn.commit()


def enabled() -> bool:
    """Persistence master switch, including the per-invocation override."""
    return PERSISTENCE_ENABLED and not _disabled_override.get()


def set_disabled_override(disabled: bool) -> None:
    """Temporarily disable all storage writes (batch tooling / tests).

    ContextVar-scoped: safe under FastAPI concurrency and Streamlit threads.
    Prefer the ``disabled()`` context manager for new code.
    """
    _disabled_override.set(disabled)


@contextmanager
def disabled() -> Iterator[None]:
    """Context manager version of ``set_disabled_override(True)``."""
    token = _disabled_override.set(True)
    try:
        yield
    finally:
        _disabled_override.reset(token)


# ---- Writers ----

def create_run(raw_input: str) -> str | None:
    """Register a new pipeline run. Returns run_id or None when disabled."""
    if not enabled():
        return None
    try:
        with _lock:
            _ensure_schema()
            run_id = f"R-{uuid.uuid4().hex[:10]}"
            preview = " ".join(raw_input.split())[:180]
            _connect().execute(
                "INSERT INTO runs (run_id, created_at, status, source_preview)"
                " VALUES (?, ?, 'processing', ?)",
                (run_id, _now(), preview),
            )
            _connect().commit()
            add_event(run_id=run_id, actor="system", action="run_created",
                      details={"questions": len(raw_input.splitlines())})
            return run_id
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.create_run failed: %s", exc)
        return None


def save_answer(
    run_id: str | None,
    question_id: str,
    question_text: str,
    draft: str,
    evidence: list[str],
    confidence: float,
    risk_flags: list[str],
    status: str,
    decided_by: str = "system",
) -> None:
    if not enabled() or not run_id:
        return
    try:
        with _lock:
            _ensure_schema()
            _connect().execute(
                """INSERT INTO answers
                   (run_id, question_id, question_text, original_draft, final_answer,
                    evidence, confidence, risk_flags, status, decided_by, decided_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(run_id, question_id) DO UPDATE SET
                     final_answer=excluded.final_answer,
                     confidence=excluded.confidence,
                     risk_flags=excluded.risk_flags,
                     status=excluded.status,
                     decided_by=excluded.decided_by,
                     decided_at=excluded.decided_at""",
                (
                    run_id, question_id, question_text, draft, draft,
                    json.dumps(evidence), confidence, json.dumps(risk_flags),
                    status, decided_by, _now(),
                ),
            )
            _connect().commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.save_answer failed: %s", exc)


def record_decision(
    run_id: str | None,
    question_id: str,
    actor: str,
    action: str,
    final_text: str,
    new_status: str,
) -> None:
    """Persist a human review outcome and append the audit event."""
    if not enabled() or not run_id:
        return
    was_edited = 0
    try:
        with _lock:
            _ensure_schema()
            row = _connect().execute(
                "SELECT original_draft FROM answers WHERE run_id=? AND question_id=?",
                (run_id, question_id),
            ).fetchone()
            original = row["original_draft"] if row else ""
            was_edited = int(bool(original) and original.strip() != final_text.strip())
            _connect().execute(
                """UPDATE answers
                   SET final_answer=?, status=?, decided_by=?, decided_at=?,
                       was_edited=?
                   WHERE run_id=? AND question_id=?""",
                (final_text, new_status, actor, _now(), was_edited, run_id, question_id),
            )
            _connect().commit()
        add_event(run_id=run_id, actor=actor, action=action, question_id=question_id,
                  details={"status": new_status, "edited": bool(was_edited)})
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.record_decision failed: %s", exc)


def complete_run(run_id: str | None, status: str, totals: dict[str, int]) -> None:
    if not enabled() or not run_id:
        return
    try:
        with _lock:
            _ensure_schema()
            _connect().execute(
                """UPDATE runs SET completed_at=?, status=?, total_questions=?
                   WHERE run_id=?""",
                (_now(), status, totals.get("total", 0), run_id),
            )
            _connect().commit()
        add_event(run_id=run_id, actor="system", action="run_completed",
                  details=dict(totals, final_status=status))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.complete_run failed: %s", exc)


def add_event(
    run_id: str | None,
    actor: str,
    action: str,
    question_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    if not enabled():
        return
    try:
        with _lock:
            _ensure_schema()
            _connect().execute(
                "INSERT INTO audit_events (ts, run_id, actor, action, question_id, details)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), run_id, actor, action, question_id,
                 json.dumps(details or {})),
            )
            _connect().commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.add_event failed: %s", exc)


# ---- Readers ----

def list_runs(limit: int = 25) -> list[dict[str, Any]]:
    if not enabled():
        return []
    try:
        _ensure_schema()
        rows = _connect().execute(
            """SELECT r.*,
                      (SELECT COUNT(*) FROM answers a WHERE a.run_id = r.run_id) AS answer_count
               FROM runs r ORDER BY r.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.list_runs failed: %s", exc)
        return []


def get_run_answers(run_id: str) -> list[dict[str, Any]]:
    if not enabled():
        return []
    try:
        _ensure_schema()
        rows = _connect().execute(
            "SELECT * FROM answers WHERE run_id=? ORDER BY question_id",
            (run_id,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["evidence"] = json.loads(d.get("evidence") or "[]")
            d["risk_flags"] = json.loads(d.get("risk_flags") or "[]")
            out.append(d)
        return out
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.get_run_answers failed: %s", exc)
        return []


def get_run_events(run_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    if not enabled():
        return []
    try:
        _ensure_schema()
        if run_id:
            rows = _connect().execute(
                "SELECT * FROM audit_events WHERE run_id=? ORDER BY event_id DESC LIMIT ?",
                (run_id, limit),
            ).fetchall()
        else:
            rows = _connect().execute(
                "SELECT * FROM audit_events ORDER BY event_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["details"] = json.loads(d.get("details") or "{}")
            out.append(d)
        return out
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.get_run_events failed: %s", exc)
        return []


def find_similar_past_answers(
    question_text: str, min_similarity: float, limit: int = 1
) -> list[dict[str, Any]]:
    """Return stored approved answers whose question closely matches.

    Uses TF-IDF cosine over the corpus of past approved questions plus the
    incoming query. Gracefully returns [] when there is no history yet.
    """
    if not enabled():
        return []
    try:
        _ensure_schema()
        rows = _connect().execute(
            """SELECT question_text, final_answer, evidence, confidence, decided_at
               FROM answers
               WHERE status IN ('auto_approved', 'human_approved')
                 AND was_edited = 0
               ORDER BY decided_at DESC LIMIT 500"""
        ).fetchall()
        if not rows:
            return []
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        docs = [r["question_text"] for r in rows]
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        matrix = vec.fit_transform([*docs, question_text])
        sims = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
        ranked = sorted(enumerate(sims), key=lambda p: p[1], reverse=True)
        out: list[dict[str, Any]] = []
        for idx, sim in ranked[:limit]:
            if sim < min_similarity:
                break
            r = rows[idx]
            out.append({
                "question_text": r["question_text"],
                "answer": r["final_answer"],
                "evidence": json.loads(r["evidence"] or "[]"),
                "confidence": r["confidence"],
                "similarity": round(float(sim), 4),
            })
        return out
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.find_similar_past_answers failed: %s", exc)
        return []


def analytics_rows(limit: int = 200) -> list[dict[str, Any]]:
    """Flat per-answer rows across recent runs for the analytics engine."""
    if not enabled():
        return []
    try:
        _ensure_schema()
        rows = _connect().execute(
            """SELECT a.*, r.created_at AS run_created_at
               FROM answers a JOIN runs r ON r.run_id = a.run_id
               ORDER BY r.created_at DESC LIMIT ?""",
            (limit * 50,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["evidence"] = json.loads(d.get("evidence") or "[]")
            d["risk_flags"] = json.loads(d.get("risk_flags") or "[]")
            out.append(d)
        return out
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.analytics_rows failed: %s", exc)
        return []


# ---- Export ----

def export_audit_csv(out_path: Path, run_id: str | None = None) -> Path | None:
    """Write the immutable audit trail to CSV. Returns the path on success."""
    events = get_run_events(run_id=run_id, limit=100000)
    if not events:
        return None
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = ["ts", "run_id", "actor", "action", "question_id", "details"]
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for e in events:
                row = {k: e.get(k, "") for k in fieldnames}
                if not isinstance(row["details"], str):
                    row["details"] = json.dumps(row["details"], sort_keys=True)
                writer.writerow(row)
        return out_path
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.export_audit_csv failed: %s", exc)
        return None
