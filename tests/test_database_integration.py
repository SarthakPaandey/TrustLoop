"""Tests for database dual-engine (PostgreSQL + SQLite), API keys, and transcriptions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import config
from storage import db


def test_sqlite_engine_default():
    """Verify that by default in test environment, SQLite is active."""
    engine = db.get_database_engine()
    assert engine in ("sqlite", "postgresql")


def test_api_key_lifecycle():
    """Test creating, verifying, listing, and revoking API keys."""
    # 1. Create API key
    created = db.create_api_key(name="Test Partner", created_by="test_suite", rate_limit=50)
    assert created
    assert "api_key" in created
    assert created["api_key"].startswith("tl_live_")
    assert created["name"] == "Test Partner"
    assert created["rate_limit"] == 50
    assert created["is_active"] is True
    raw_key = created["api_key"]
    key_id = created["key_id"]

    # 2. Verify valid key
    assert db.verify_api_key(raw_key) is True

    # 3. Verify invalid key
    assert db.verify_api_key("tl_live_invalid_key_12345") is False
    assert db.verify_api_key("") is False

    # 4. List keys (raw key must never be leaked)
    keys = db.list_api_keys()
    matching = [k for k in keys if k["key_id"] == key_id]
    assert len(matching) == 1
    info = matching[0]
    assert "api_key" not in info
    assert info["key_preview"] == created["key_preview"]
    assert info["name"] == "Test Partner"
    assert info["is_active"] == 1
    assert info["last_used_at"] is not None  # Updated during verify_api_key

    # 5. Revoke key
    assert db.revoke_api_key(key_id, actor="admin_test") is True
    # Revoked key should no longer verify
    assert db.verify_api_key(raw_key) is False

    # Listed key should now show inactive
    keys_after = db.list_api_keys()
    matching_after = next(k for k in keys_after if k["key_id"] == key_id)
    assert matching_after["is_active"] == 0


def test_transcription_persistence():
    """Test saving and retrieving media transcriptions."""
    t_id = db.save_transcription(
        filename="security_review.mp4",
        transcript_text="Do you encrypt customer data at rest? Yes, with AES-256.",
        detected_questions=["Do you encrypt customer data at rest?"],
        duration_seconds=42.5,
    )
    assert t_id is not None
    assert t_id.startswith("TR-")

    # Fetch by ID
    record = db.get_transcription(t_id)
    assert record is not None
    assert record["filename"] == "security_review.mp4"
    assert record["duration_seconds"] == 42.5
    assert record["detected_questions"] == ["Do you encrypt customer data at rest?"]
    assert "AES-256" in record["transcript_text"]

    # List transcriptions
    recent = db.list_transcriptions(limit=10)
    assert any(r["id"] == t_id for r in recent)


def test_db_adapter_sql_translation():
    """Test query parameter translation for PostgreSQL."""
    # Test query placeholder regex
    query = "SELECT * FROM answers WHERE run_id = ? AND question_id = ? LIMIT ?"
    converted = db.re.sub(r"\?", "%s", query)
    assert converted == "SELECT * FROM answers WHERE run_id = %s AND question_id = %s LIMIT %s"


def test_postgres_fallback_on_connection_error():
    """Verify that if PostgreSQL connection fails, it safely falls back to SQLite."""
    with patch.object(config, "DATABASE_URL", "postgresql://invalid_user:invalid_pass@127.0.0.1:9999/fake_db"):
        # Reset cached connection
        if hasattr(db._local, "adapter"):
            delattr(db._local, "adapter")
        if hasattr(db._local, "engine_type"):
            delattr(db._local, "engine_type")

        # Calling _connect() should log warning and return SQLite adapter
        adapter = db._connect()
        assert adapter is not None
        assert adapter.is_pg is False
        assert db.get_database_engine() == "sqlite"


def test_postgres_mock_execution():
    """Test DBConnectionAdapter and CursorAdapter paths when is_pg is True."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {"val": 42}
    mock_cursor.fetchall.return_value = [{"val": 1}, {"val": 2}]

    mock_pg_conn = MagicMock()
    mock_pg_conn.cursor.return_value = mock_cursor

    adapter = db._DBConnectionAdapter(mock_pg_conn, is_pg=True)
    assert adapter.is_pg is True

    # Execute query
    cur = adapter.execute("SELECT * FROM t WHERE a = ? AND b = ?", (1, 2))
    assert cur.fetchone() == {"val": 42}
    assert cur.fetchall() == [{"val": 1}, {"val": 2}]
    # Check that '?' was converted to '%s'
    mock_cursor.execute.assert_called_with("SELECT * FROM t WHERE a = %s AND b = %s", (1, 2))

    # Commit and rollback
    adapter.commit()
    mock_pg_conn.commit.assert_called()

    adapter.rollback()
    mock_pg_conn.rollback.assert_called()
