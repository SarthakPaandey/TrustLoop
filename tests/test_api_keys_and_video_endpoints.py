"""End-to-end tests for FastAPI developer API key management and video processing endpoints."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api import app
from storage import db


@pytest.fixture
def client():
    return TestClient(app)


def test_api_key_management_endpoints(client):
    """Test generating, listing, and revoking API keys through REST endpoints."""
    # 1. Create API key
    res = client.post(
        "/api/v1/auth/keys",
        json={"name": "Integration Test Key", "rate_limit": 150},
    )
    assert res.status_code == 201
    data = res.json()
    assert "api_key" in data
    assert data["api_key"].startswith("tl_live_")
    assert data["name"] == "Integration Test Key"
    assert data["rate_limit"] == 150
    assert data["is_active"] is True
    api_key = data["api_key"]
    key_id = data["key_id"]

    # 2. List keys
    list_res = client.get("/api/v1/auth/keys")
    assert list_res.status_code == 200
    keys = list_res.json()
    matching = [k for k in keys if k["key_id"] == key_id]
    assert len(matching) == 1
    # Full secret must not be exposed in list
    assert "api_key" not in matching[0]

    # 3. Authenticate with the generated key via X-API-Key
    auth_res = client.get("/api/v1/stats", headers={"X-API-Key": api_key})
    assert auth_res.status_code == 200

    # 4. Authenticate with Bearer token
    bearer_res = client.get("/api/v1/stats", headers={"Authorization": f"Bearer {api_key}"})
    assert bearer_res.status_code == 200

    # 5. Revoke key
    del_res = client.delete(f"/api/v1/auth/keys/{key_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "revoked"

    # 6. Revoked key must fail authentication
    fail_res = client.get("/api/v1/stats", headers={"X-API-Key": api_key})
    assert fail_res.status_code == 401


def test_invalid_api_key_rejected(client):
    """Test that invalid keys provided in headers are rejected with 401."""
    res = client.get("/api/v1/stats", headers={"X-API-Key": "tl_live_completely_fake_key"})
    assert res.status_code == 401
    assert "Invalid or inactive API key" in res.json()["detail"]


def test_auth_enforced_when_trustloop_api_key_set(client):
    """When TRUSTLOOP_API_KEY is configured in env, all requests require valid auth."""
    with patch("api.API_AUTH_KEY", "master_secret_123"):
        # Without key -> 401
        res = client.get("/api/v1/stats")
        assert res.status_code == 401

        # With master key -> 200
        res = client.get("/api/v1/stats", headers={"X-API-Key": "master_secret_123"})
        assert res.status_code == 200

        # With valid DB key -> 200
        created = db.create_api_key(name="Client Under Master Auth")
        try:
            res = client.get("/api/v1/stats", headers={"X-API-Key": created["api_key"]})
            assert res.status_code == 200
        finally:
            db.revoke_api_key(created["key_id"])



def test_video_transcribe_endpoint(client):
    """Test /api/v1/video/transcribe endpoint with media file upload."""
    dummy_audio = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00")
    files = {"file": ("vendor_assessment.wav", dummy_audio, "audio/wav")}

    res = client.post("/api/v1/video/transcribe", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["filename"] == "vendor_assessment.wav"
    assert "transcript" in data
    assert "detected_questions" in data
    assert len(data["detected_questions"]) > 0


def test_video_run_pipeline_endpoint(client):
    """Test /api/v1/video/run endpoint that parses video dialogue and runs verification."""
    dummy_video = io.BytesIO(b"\x00\x00\x00 ftypisom")
    files = {"file": ("compliance_meeting.mp4", dummy_video, "video/mp4")}

    res = client.post("/api/v1/video/run", files=files, data={"persist": "true"})
    assert res.status_code == 200
    data = res.json()
    assert "run_id" in data
    assert "questions" in data
    assert "answers" in data
    assert len(data["questions"]) > 0
    assert len(data["answers"]) > 0
    assert data["final_status"] in ("completed", "reviewing", "processing")
    assert "quality" in data


def test_kb_video_upload_endpoint(client):
    """Test /api/v1/kb/video endpoint to ingest video transcript into RAG index."""
    from pathlib import Path
    import config
    target_file = config.KB_DIR / "dr_policy_briefing.md"
    try:
        dummy_video = io.BytesIO(b"\x00\x00\x00 ftypisom")
        files = {"file": ("dr_policy_briefing.mp4", dummy_video, "video/mp4")}

        res = client.post("/api/v1/kb/video", files=files, data={"doc_name": "dr_policy_briefing.md"})
        assert res.status_code == 201
        data = res.json()
        assert data["created"] is True
        assert data["filename"] == "dr_policy_briefing.md"
        assert data["chunks"] > 0
        assert data["total_documents"] > 0
    finally:
        if target_file.exists():
            target_file.unlink()
        from retrieval import reset_vector_store
        reset_vector_store()



def test_video_transcriptions_list_endpoint(client):
    """Test listing persisted transcriptions via API."""
    res = client.get("/api/v1/video/transcriptions")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_video_endpoint_unsupported_format(client):
    """Test rejection of unsupported file extensions."""
    files = {"file": ("document.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    res = client.post("/api/v1/video/transcribe", files=files)
    assert res.status_code == 422
    assert "Unsupported media format" in res.json()["detail"]
