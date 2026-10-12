"""API coverage for the send-readiness score."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api import app


def _client() -> TestClient:
    return TestClient(app)


def test_endpoint_flags_a_contradiction():
    payload = {
        "answers": [
            {
                "question_id": "Q-yes",
                "question_text": "Do you encrypt data at rest?",
                "draft": "Yes. Customer data is encrypted at rest with AES-256.",
                "evidence": ["encryption_policy.md"],
                "confidence": 0.9,
                "status": "auto_approved",
            },
            {
                "question_id": "Q-no",
                "question_text": "Is data at rest encrypted?",
                "draft": "Data at rest is not encrypted.",
                "evidence": ["encryption_policy.md"],
                "confidence": 0.9,
                "status": "auto_approved",
            },
        ]
    }
    response = _client().post("/api/v1/quality", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["ready_to_send"] is False
    assert body["counts"]["contradictions"] == 1


def test_bad_status_is_rejected():
    response = _client().post("/api/v1/quality", json={
        "answers": [{
            "question_id": "Q-1",
            "question_text": "Do you encrypt data at rest?",
            "status": "teleport",
        }]
    })
    assert response.status_code == 422


def test_run_response_includes_readiness():
    response = _client().post("/api/v1/run", json={
        "text": "Do you encrypt data at rest?",
        "persist": False,
    })
    assert response.status_code == 200
    quality = response.json()["quality"]
    assert quality["ready_to_send"] is True
    assert quality["score"] == 100
    assert quality["counts"]["contradictions"] == 0
