"""Tests for the v2 upgrades: hybrid retrieval, calibrated confidence,
claim-level verification, persistence/audit, graph HITL + memory, analytics,
API auth/batch, and Slack delivery."""

from __future__ import annotations

import pytest

from actions import send_slack_notification
from agents import parse_questionnaire, research_answer, verify_answer
from graph import (
    apply_review_decision,
    resume_pipeline,
    run_pipeline,
)
from models import Answer
from retrieval import find_chunk_by_citation, get_vector_store
from storage import db


def _answer_for(text: str):
    q = parse_questionnaire(text)[0]
    return q, verify_answer(research_answer(q), q)


# ============================================================================
# Hybrid retrieval
# ============================================================================

class TestHybridRetrieval:
    def test_relevant_query_returns_ordered_hits(self):
        hits = get_vector_store().search("Do you encrypt data at rest?")
        assert hits
        scores = [s for _, s in hits]
        assert scores == sorted(scores, reverse=True)
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_off_topic_query_returns_nothing(self):
        assert get_vector_store().search("What is your favorite color?") == []

    def test_empty_query_returns_nothing(self):
        assert get_vector_store().search("   ") == []

    def test_bm25_only_signal_still_found(self):
        # "AES-256" is rare terminology — BM25 should surface it even if the
        # TF-IDF cosine alone would be weak.
        hits = get_vector_store().search("AES 256 key rotation policy")
        assert any("encryption" in c.source for c, _ in hits)

    def test_citation_lookup_roundtrip(self):
        chunk = find_chunk_by_citation("encryption_policy.md#encryption_at_rest")
        assert chunk is not None


# ============================================================================
# Calibrated confidence
# ============================================================================

class TestCalibration:
    def _conf(self, top: float, runner: float = 0.1) -> float:
        from agents.researcher import _compute_confidence
        hits = [
            (find_chunk_by_citation("encryption_policy.md#encryption_at_rest"), top),
            (find_chunk_by_citation("data_storage_policy.md#overview"), runner),
        ]
        q = parse_questionnaire("Do you encrypt data at rest?")[0]
        return _compute_confidence(hits, q)

    def test_monotonic_in_relevance(self):
        values = [self._conf(t) for t in (0.2, 0.4, 0.6, 0.8, 1.0)]
        assert values == sorted(values)
        assert all(0.0 < v <= 0.95 for v in values)

    def test_strong_match_crosses_threshold(self):
        assert self._conf(1.0) >= 0.70

    def test_weak_match_below_threshold(self):
        assert self._conf(0.15) < 0.70

    def test_encryption_end_to_end_auto_approves(self):
        _q, a = _answer_for("Do you encrypt data at rest?")
        assert a.status == "auto_approved"
        assert a.confidence >= 0.70


# ============================================================================
# Claim-level verification layer
# ============================================================================

class TestClaimGrounding:
    def test_unverifiable_sentence_flagged(self):
        cite = "encryption_policy.md#encryption_at_rest"  # resolves in live KB
        q = parse_questionnaire("Do you encrypt data at rest?")[0]
        a = Answer(
            question_id=q.id, question_text=q.text,
            draft="Data is encrypted with AES-256. We also provide complimentary "
                  "pony rentals for every enterprise customer contract.",
            evidence=[cite], confidence=0.9,
        )
        result = verify_answer(a, q)
        assert any("[UNSUPPORTED_CLAIM]" in f for f in result.risk_flags)
        assert result.status == "needs_review"

    def test_grounded_negative_not_flagged(self):
        q = parse_questionnaire("Do you have a BAA process?")[0]
        a = Answer(
            question_id=q.id, question_text=q.text,
            draft="Acme SaaS does not sign Business Associate Agreements because "
                  "it is not HIPAA certified.",
            evidence=["compliance_certifications.md#certifications_not_held"],
            confidence=0.85,
        )
        result = verify_answer(a, q)
        assert not any("[CERT_WARNING]" in f for f in result.risk_flags)
        assert result.status == "auto_approved"

    def test_cert_named_in_question_always_escalates(self):
        q, a = _answer_for("Are you HIPAA certified?")
        assert a.status == "needs_review"
        assert any("[CERT_WARNING]" in f for f in a.risk_flags)

    def test_synthetic_citations_do_not_false_positive(self):
        q = parse_questionnaire("What is MFA?")[0]
        a = Answer(
            question_id=q.id, question_text=q.text,
            draft="MFA is supported via TOTP and WebAuthn.",
            evidence=["fake_doc.md#made_up_section"], confidence=0.9,
        )
        result = verify_answer(a, q)
        assert result.status == "auto_approved"

    def test_soc2_regression_fixed(self):
        _q, a = _answer_for("Are you SOC 2 Type II certified?")
        assert a.status == "auto_approved", a.risk_flags


# ============================================================================
# Persistence + audit trail
# ============================================================================

class TestStorage:
    def test_run_lifecycle_and_audit(self):
        run_id = db.create_run("test questionnaire")
        assert run_id
        db.save_answer(run_id, "Q-1", "Q?", "draft text",
                       ["doc.md#a"], 0.8, [], "needs_review")
        db.record_decision(run_id, "Q-1", "jane", "review_edit",
                           "edited text", "human_approved")
        rows = db.get_run_answers(run_id)
        assert len(rows) == 1
        assert rows[0]["final_answer"] == "edited text"
        assert rows[0]["was_edited"] == 1
        assert rows[0]["decided_by"] == "jane"
        events = db.get_run_events(run_id=run_id)
        actions = {e["action"] for e in events}
        assert {"run_created", "review_edit"} <= actions
        db.complete_run(run_id, "completed", {"total": 1})
        runs = {r["run_id"] for r in db.list_runs(limit=50)}
        assert run_id in runs

    def test_audit_csv_export(self, tmp_path):
        run_id = db.create_run("csv export probe")
        db.add_event(run_id, "tester", "probe_action")
        out = tmp_path / "audit.csv"
        path = db.export_audit_csv(out, run_id=run_id)
        assert path and path.exists()
        content = path.read_text()
        assert "probe_action" in content and "run_created" in content

    def test_past_answer_reuse_lookup(self):
        run_id = db.create_run("reuse lookup probe")
        db.save_answer(run_id, "Q-R1", "Do you encrypt data at rest?",
                       "Yes — AES-256.", ["encryption_policy.md#x"], 0.9, [],
                       "auto_approved")
        hits = db.find_similar_past_answers(
            "Do you encrypt data at rest?", min_similarity=0.85)
        assert hits and hits[0]["similarity"] >= 0.85

    def test_disabled_persistence_is_noop(self, monkeypatch):
        monkeypatch.setattr(db, "PERSISTENCE_ENABLED", False)
        assert db.enabled() is False
        assert db.list_runs() == []


# ============================================================================
# Graph: HITL gate, resume, memory
# ============================================================================

class TestGraphHITLAndMemory:
    def test_flagged_run_halts_then_completes(self):
        state = run_pipeline(
            "Do you encrypt data at rest?\nAre you HIPAA certified?", persist=False)
        assert state["final_status"] == "reviewing"
        for qid in list(state["review_queue"]):
            state = apply_review_decision(state, qid, "approve", actor="t")
        assert state["review_queue"] == []
        completed = resume_pipeline(state)
        assert completed["final_status"] == "completed"
        assert any(a.startswith("workbook_exported:") for a in completed["actions_taken"])

    def test_resume_guard_blocks_open_queue(self):
        state = run_pipeline("Are you HIPAA certified?", persist=False)
        with pytest.raises(ValueError):
            resume_pipeline(state)

    def test_reject_decision(self):
        state = run_pipeline("Are you FedRAMP authorized?", persist=False)
        qid = state["review_queue"][0]
        state = apply_review_decision(state, qid, "reject", actor="t")
        answers = {a.question_id: a for a in state["answers"]}
        assert answers[qid].status == "rejected"

    def test_invalid_action_raises(self):
        state = run_pipeline("Are you HIPAA certified?", persist=False)
        with pytest.raises(ValueError):
            apply_review_decision(state, state["review_queue"][0], "teleport")

    def test_duplicate_questions_share_one_answer(self):
        raw = "What is your MFA policy?\nwhat is your MFA policy?"
        state = run_pipeline(raw, persist=False)
        drafts = [a.draft for a in state["answers"]]
        assert len(drafts) == 2
        assert "duplicate of question" in drafts[1]

    def test_cross_run_answer_reuse(self):
        first = run_pipeline("Do you encrypt data at rest?", persist=True)
        second = run_pipeline("Do you encrypt data at rest?", persist=True)
        assert "Reused previously approved answer" in second["answers"][0].draft
        # Reuse must not degrade safety: still auto-approved & grounded.
        assert second["answers"][0].status == "auto_approved"
        assert first["answers"][0].evidence


# ============================================================================
# Analytics engine
# ============================================================================

class TestAnalytics:
    def _rows(self):
        base = {"question_text": "Do you encrypt data at rest?",
                "category": "technical", "confidence": 0.9}
        return [
            {"run_id": "R-1", "question_id": "Q-A1", "status": "auto_approved",
             "risk_flags": [], "was_edited": 0,
             "run_created_at": "2026-01-01T00:00:00", **base},
            {"run_id": "R-1", "question_id": "Q-A2", "status": "human_approved",
             "risk_flags": [], "was_edited": 1,
             "run_created_at": "2026-01-01T00:00:00", **base},
            {"run_id": "R-2", "question_id": "Q-B1", "status": "needs_review",
             "risk_flags": ["[LOW_CONFIDENCE] low", "[CERT_WARNING] hipaa"],
             "was_edited": 0, "run_created_at": "2026-01-02T00:00:00", **base},
        ]

    def test_overview_counts_and_rates(self):
        from analytics import overview
        ov = overview(self._rows())
        assert ov["total_answers"] == 3
        assert ov["resolution_rate"] == pytest.approx(66.7)
        assert ov["edit_rate_pct"] == pytest.approx(33.3)

    def test_flag_frequency_codes(self):
        from analytics import flag_frequency
        ff = flag_frequency(self._rows())
        codes = [f["code"] for f in ff]
        assert "LOW_CONFIDENCE" in codes and "CERT_WARNING" in codes
        counts = {f["code"]: f["count"] for f in ff}
        assert counts["LOW_CONFIDENCE"] == 1

    def test_trend_ordered_and_bounded(self):
        from analytics import auto_rate_trend
        trend = auto_rate_trend(self._rows())
        # R-1: both answers resolved -> 100%. R-2: single open item -> 0%.
        assert [t["rate_pct"] for t in trend] == [100.0, 0.0]

    def test_compute_analytics_shape(self):
        from analytics import compute_analytics
        data = compute_analytics(self._rows())
        assert data["has_data"]
        assert set(data) >= {"overview", "flag_frequency",
                             "confidence_by_category", "auto_rate_trend"}

    def test_empty_rows_safe(self):
        from analytics import compute_analytics
        assert compute_analytics([])["has_data"] is False


# ============================================================================
# API: auth, batch, review endpoints
# ============================================================================

class TestAPI:
    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient

        from api import app
        return TestClient(app)

    def test_health_open(self, client):
        assert client.get("/api/v1/health").status_code == 200

    def test_run_endpoint(self, client):
        r = client.post("/api/v1/run", json={
            "text": "What is your MFA policy?", "persist": False})
        assert r.status_code == 200
        body = r.json()
        assert body["summary"]["total"] == 1

    def test_batch_endpoint(self, client):
        r = client.post("/api/v1/run/batch", json={
            "texts": ["What is your MFA policy?", "Are you HIPAA certified?"],
            "persist": False})
        assert r.status_code == 200
        bodies = r.json()
        assert len(bodies) == 2
        statuses = {b["final_status"] for b in bodies}
        assert "completed" in statuses and "reviewing" in statuses

    def test_batch_limit_enforced(self, client):
        r = client.post("/api/v1/run/batch", json={"texts": ["q?"] * 26})
        assert r.status_code == 413

    def test_auth_enforced_when_configured(self, client, monkeypatch):
        monkeypatch.setattr("api.API_AUTH_KEY", "sekrit")
        assert client.get("/api/v1/runs").status_code == 401
        ok = client.get("/api/v1/runs", headers={"X-API-Key": "sekrit"})
        assert ok.status_code == 200
        assert client.get("/api/v1/health").status_code == 200  # health stays open

    def test_decision_and_resume_flow(self, client):
        r = client.post("/api/v1/run", json={
            "text": "Are you HIPAA certified?", "persist": False})
        state = r.json()["state"]
        assert state and state["review_queue"], "run should pause with a queue"
        qid = state["review_queue"][0]

        d = client.post("/api/v1/run/decision", json={
            "state": state, "question_id": qid, "action": "approve"})
        assert d.status_code == 200
        updated = d.json()["state"]
        assert updated["review_queue"] == []

        res = client.post("/api/v1/run/resume", json={"state": updated})
        assert res.status_code == 200
        body = res.json()
        assert body["final_status"] == "completed"
        assert any(a.startswith("workbook_exported:")
                   for a in (body["actions_taken"] or []))

    def test_stats_lists_new_guardrail(self, client):
        codes = client.get("/api/v1/stats").json()["guardrails"]
        assert "UNSUPPORTED_CLAIM" in codes


# ============================================================================
# Slack webhook delivery
# ============================================================================

class TestSlackDelivery:
    def _answers(self):
        from samples.demo_data import DEMO_ANSWERS
        return list(DEMO_ANSWERS)

    def test_dry_run_without_url(self, monkeypatch):
        monkeypatch.setattr("actions.slack_notifier.SLACK_WEBHOOK_URL", "")
        result = send_slack_notification(self._answers())
        assert result["dry_run"] and not result["delivered"]

    def test_delivery_failure_never_raises(self):
        result = send_slack_notification(
            self._answers(), webhook_url="http://127.0.0.1:9/unreachable")
        assert result["delivered"] is False
