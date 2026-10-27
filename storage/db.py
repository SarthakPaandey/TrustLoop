"""Persistence layer: PostgreSQL and SQLite backed run history, decisions, API keys, and audit trail.

Design goals:
- Dual-engine: PostgreSQL (when configured) with graceful SQLite fallback.
- Every mutation appends an immutable audit_events row — who did what, when.
- All public functions degrade gracefully (log + safe default) so a storage
  failure can never crash the pipeline or the UI mid-demo.

The DB path comes from config.DB_PATH (override with TRUSTLOOP_DB_PATH, used
by tests to isolate fixtures). PostgreSQL connection comes from config.DATABASE_URL.
"""

from __future__ import annotations

import contextvars
import csv
import hashlib
import json
import logging
import re
import secrets
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import config
from config import DB_PATH, PERSISTENCE_ENABLED, is_postgres_url

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

CREATE TABLE IF NOT EXISTS api_keys (
    key_id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL,
    key_preview TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    rate_limit INTEGER DEFAULT 100,
    created_by TEXT DEFAULT 'admin'
);

CREATE TABLE IF NOT EXISTS transcriptions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    filename TEXT NOT NULL,
    duration_seconds REAL NOT NULL DEFAULT 0.0,
    transcript_text TEXT NOT NULL,
    detected_questions TEXT NOT NULL DEFAULT '[]',
    run_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_answers_run ON answers(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_events(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_transcriptions_run ON transcriptions(run_id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class _CursorAdapter:
    def __init__(self, cursor, is_pg: bool = False):
        self.cursor = cursor
        self.is_pg = is_pg

    def fetchone(self) -> dict[str, Any] | None:
        row = self.cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self) -> list[dict[str, Any]]:
        rows = self.cursor.fetchall()
        return [dict(r) for r in rows]

    def __iter__(self):
        for r in self.cursor:
            yield dict(r)


class _DBConnectionAdapter:
    def __init__(self, raw_conn, is_pg: bool = False):
        self.conn = raw_conn
        self.is_pg = is_pg

    def execute(self, sql: str, params: tuple | list = ()):
        if self.is_pg:
            # Replace '?' with '%s' for psycopg2 query parameterization
            sql_pg = re.sub(r"\?", "%s", sql)
            import psycopg2.extras
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql_pg, params)
            return _CursorAdapter(cur, is_pg=True)
        else:
            cur = self.conn.execute(sql, params)
            return _CursorAdapter(cur, is_pg=False)

    def executescript(self, script: str) -> None:
        if self.is_pg:
            with self.conn.cursor() as cur:
                cur.execute(script)
            self.conn.commit()
        else:
            self.conn.executescript(script)

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()


def _connect() -> _DBConnectionAdapter:
    adapter = getattr(_local, "adapter", None)
    target_engine = "postgres" if (is_postgres_url() and config.DATABASE_URL) else "sqlite"
    cached_engine = getattr(_local, "engine_type", None)

    if adapter is not None and cached_engine == target_engine:
        if target_engine == "sqlite":
            if getattr(_local, "db_path", None) == str(DB_PATH):
                return adapter
        else:
            try:
                if not adapter.conn.closed:
                    return adapter
            except Exception:
                pass

    if target_engine == "postgres":
        try:
            import psycopg2
            pg_conn = psycopg2.connect(config.DATABASE_URL, connect_timeout=5)
            adapter = _DBConnectionAdapter(pg_conn, is_pg=True)
            _local.adapter = adapter
            _local.engine_type = "postgres"
            logger.info("Connected to PostgreSQL backend: %s", config.DATABASE_URL.split("@")[-1])
            return adapter
        except Exception as exc:
            logger.warning("Failed to connect to PostgreSQL (%s). Falling back to SQLite.", exc)

    # Fallback / Default: SQLite
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    sqlite_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_conn.execute("PRAGMA journal_mode=WAL")
    sqlite_conn.execute("PRAGMA foreign_keys=ON")
    adapter = _DBConnectionAdapter(sqlite_conn, is_pg=False)
    _local.adapter = adapter
    _local.engine_type = "sqlite"
    _local.db_path = str(DB_PATH)
    return adapter


def _ensure_schema() -> None:
    conn = _connect()
    if conn.is_pg:
        pg_schema = _SCHEMA.replace(
            "event_id INTEGER PRIMARY KEY AUTOINCREMENT", "event_id SERIAL PRIMARY KEY"
        )
        conn.executescript(pg_schema)
    else:
        conn.executescript(_SCHEMA)
    conn.commit()


def get_database_engine() -> str:
    """Return currently active database engine name ('postgresql' or 'sqlite')."""
    conn = _connect()
    return "postgresql" if conn.is_pg else "sqlite"


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


# ---- API Key Management ----

def create_api_key(
    name: str, created_by: str = "admin", rate_limit: int = 100
) -> dict[str, Any]:
    """Generate and persist a new API key. Returns raw key once for copy."""
    if not enabled():
        return {}
    try:
        with _lock:
            _ensure_schema()
            raw_key = f"tl_live_{secrets.token_urlsafe(24)}"
            key_id = f"key_{uuid.uuid4().hex[:10]}"
            key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
            key_preview = f"{raw_key[:11]}...{raw_key[-4:]}"
            now = _now()
            _connect().execute(
                """INSERT INTO api_keys
                   (key_id, key_hash, key_preview, name, created_at, is_active, rate_limit, created_by)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                (key_id, key_hash, key_preview, name.strip() or "Default Key", now, rate_limit, created_by),
            )
            _connect().commit()
            add_event(
                run_id=None,
                actor=created_by,
                action="api_key_created",
                details={"key_id": key_id, "name": name, "preview": key_preview},
            )
            return {
                "key_id": key_id,
                "name": name.strip() or "Default Key",
                "api_key": raw_key,
                "key_preview": key_preview,
                "created_at": now,
                "rate_limit": rate_limit,
                "is_active": True,
            }
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.create_api_key failed: %s", exc)
        return {}


def verify_api_key(raw_key: str) -> bool:
    """Validate raw key against active keys; updates last_used_at timestamp on match."""
    if not enabled() or not raw_key:
        return False
    try:
        with _lock:
            _ensure_schema()
            key_hash = hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()
            row = _connect().execute(
                "SELECT key_id FROM api_keys WHERE key_hash = ? AND is_active = 1",
                (key_hash,),
            ).fetchone()
            if row:
                _connect().execute(
                    "UPDATE api_keys SET last_used_at = ? WHERE key_id = ?",
                    (_now(), row["key_id"]),
                )
                _connect().commit()
                return True
            return False
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.verify_api_key failed: %s", exc)
        return False


def list_api_keys() -> list[dict[str, Any]]:
    """Return all API keys with masked previews (never raw keys)."""
    if not enabled():
        return []
    try:
        _ensure_schema()
        rows = _connect().execute(
            """SELECT key_id, name, key_preview, created_at, last_used_at, is_active, rate_limit, created_by
               FROM api_keys ORDER BY created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.list_api_keys failed: %s", exc)
        return []


def revoke_api_key(key_id: str, actor: str = "admin") -> bool:
    """Deactivate an API key."""
    if not enabled() or not key_id:
        return False
    try:
        with _lock:
            _ensure_schema()
            _connect().execute(
                "UPDATE api_keys SET is_active = 0 WHERE key_id = ?",
                (key_id,),
            )
            _connect().commit()
            add_event(
                run_id=None,
                actor=actor,
                action="api_key_revoked",
                details={"key_id": key_id},
            )
            return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.revoke_api_key failed: %s", exc)
        return False


# ---- Audio / Video Transcriptions ----

def save_transcription(
    filename: str,
    transcript_text: str,
    detected_questions: list[str],
    duration_seconds: float = 0.0,
    run_id: str | None = None,
) -> str | None:
    """Persist video/audio transcription and extracted questions."""
    if not enabled():
        return None
    try:
        with _lock:
            _ensure_schema()
            t_id = f"TR-{uuid.uuid4().hex[:10]}"
            _connect().execute(
                """INSERT INTO transcriptions
                   (id, created_at, filename, duration_seconds, transcript_text, detected_questions, run_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    t_id,
                    _now(),
                    filename,
                    duration_seconds,
                    transcript_text,
                    json.dumps(detected_questions),
                    run_id,
                ),
            )
            _connect().commit()
            add_event(
                run_id=run_id,
                actor="system",
                action="transcription_saved",
                details={
                    "transcription_id": t_id,
                    "filename": filename,
                    "questions_count": len(detected_questions),
                },
            )
            return t_id
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.save_transcription failed: %s", exc)
        return None


def list_transcriptions(limit: int = 25) -> list[dict[str, Any]]:
    """List recent video/audio transcriptions."""
    if not enabled():
        return []
    try:
        _ensure_schema()
        rows = _connect().execute(
            "SELECT * FROM transcriptions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["detected_questions"] = json.loads(d.get("detected_questions") or "[]")
            out.append(d)
        return out
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.list_transcriptions failed: %s", exc)
        return []


def get_transcription(transcription_id: str) -> dict[str, Any] | None:
    """Fetch one transcription record by ID."""
    if not enabled() or not transcription_id:
        return None
    try:
        _ensure_schema()
        row = _connect().execute(
            "SELECT * FROM transcriptions WHERE id = ?",
            (transcription_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["detected_questions"] = json.loads(d.get("detected_questions") or "[]")
        return d
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("storage.get_transcription failed: %s", exc)
        return None

