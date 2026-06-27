"""Comprehensive test suite for TrustLoop.

Covers:
- TC-001 through TC-006: Original PRD test scenarios
- Extended routing precision tests
- Verifier edge cases
- Researcher grounding tests
- Demo data integrity
- Export and action generation
- Pipeline end-to-end
"""

from __future__ import annotations

import pytest

from agents import parse_questionnaire, research_answer, verify_answer
from graph import run_pipeline
from models import Answer, Question
from actions import (
    build_slack_notification,
    draft_prospect_email,
    export_workbook,
    summarize_run,
)


def _answer_for(text: str) -> tuple[Question, Answer]:
    questions = parse_questionnaire(text)
    assert questions, f"intake produced no questions for: {text!r}"
    q = questions[0]
    a = research_answer(q)
    a = verify_answer(a, q)
    return q, a


# ============================================================================
# TC-001 through TC-006: Original PRD scenarios
# ============================================================================

def test_tc001_encryption_at_rest_auto_approves():
    q, a = _answer_for("Do you encrypt data at rest?")
    assert a.status == "auto_approved", a.risk_flags
    assert "AES-256".lower() in a.draft.lower()
    assert any("encryption_policy.md" in cite for cite in a.evidence)
    assert a.confidence >= 0.70


def test_tc002_hipaa_escalates():
    q, a = _answer_for("Are you HIPAA certified?")
    assert a.status == "needs_review"
    assert any("[CERT_WARNING]" in f for f in a.risk_flags)
    assert "is not" in a.draft.lower() or "does not" in a.draft.lower() \
        or "NOT" in a.draft or "no_evidence" in a.draft.lower() \
        or "not hipaa" in a.draft.lower()


def test_tc003_geographic_storage_escalates():
    q, a = _answer_for("Where is customer data stored?")
    assert a.status == "needs_review"
    assert any("[DATA_RESIDENCY]" in f for f in a.risk_flags)


def test_tc004_off_topic_zero_confidence():
    q, a = _answer_for("What is your favorite color?")
    assert a.status == "needs_review"
    assert a.confidence == 0.0
    assert a.evidence == []
    assert any("[MISSING_EVIDENCE]" in f for f in a.risk_flags)


def test_tc005_absolute_guarantee_flagged():
    q, a = _answer_for("Do you guarantee zero breaches?")
    assert a.status == "needs_review"
    assert any("[LEGAL_RISK]" in f for f in a.risk_flags)


def test_tc006_empty_input_does_not_crash():
    state = run_pipeline("")
    assert state["final_status"] in {"completed", "processing", "reviewing"}
    assert state["questions"] == []
    assert state["answers"] == []
    assert state["review_queue"] == []


# ============================================================================
# Extended routing precision tests
# ============================================================================

@pytest.mark.parametrize(
    "question_text, expected_status",
    [
        ("Do you encrypt data at rest?", "auto_approved"),
        ("Are you HIPAA certified?", "needs_review"),
        ("Where is customer data stored?", "needs_review"),
        ("What is your favorite color?", "needs_review"),
        ("Do you guarantee zero breaches?", "needs_review"),
        ("Do you encrypt data in transit?", "auto_approved"),
        ("What is your MFA policy?", "auto_approved"),
        ("Are you SOC 2 Type II certified?", "auto_approved"),
        ("Are you PCI DSS certified?", "needs_review"),
        ("Are you FedRAMP authorized?", "needs_review"),
        ("What is your data retention policy?", "auto_approved"),
        ("Will you indemnify us for data loss?", "needs_review"),
    ],
)
def test_routing_precision(question_text: str, expected_status: str):
    _q, a = _answer_for(question_text)
    assert a.status == expected_status


# ============================================================================
# Verifier edge cases
# ============================================================================

class TestVerifierEdgeCases:
    def test_empty_answer_gets_missing_evidence(self):
        q = Question(id="test", text="Test question", category="technical")
        a = Answer(
            question_id="test",
            question_text="Test question",
            draft="No evidence found.",
            evidence=[],
            confidence=0.0,
        )
        result = verify_answer(a, q)
        assert any("[MISSING_EVIDENCE]" in f for f in result.risk_flags)
        assert result.status == "needs_review"

    def test_low_confidence_routes_to_review(self):
        q = Question(id="test", text="Test question", category="technical")
        a = Answer(
            question_id="test",
            question_text="Test question",
            draft="Some answer.",
            evidence=["doc.md#section"],
            confidence=0.30,
        )
        result = verify_answer(a, q)
        assert any("[LOW_CONFIDENCE]" in f for f in result.risk_flags)
        assert result.status == "needs_review"

    def test_legal_category_always_routes(self):
        q = Question(id="test", text="Legal question", category="legal")
        a = Answer(
            question_id="test",
            question_text="Legal question",
            draft="Some answer.",
            evidence=["doc.md#section"],
            confidence=0.90,
        )
        result = verify_answer(a, q)
        assert any("[ROUTING]" in f for f in result.risk_flags)
        assert result.status == "needs_review"

    def test_clean_technical_auto_approves(self):
        q = Question(id="test", text="What is MFA?", category="technical")
        a = Answer(
            question_id="test",
            question_text="What is MFA?",
            draft="MFA is supported via TOTP and WebAuthn.",
            evidence=["access_control.md#mfa"],
            confidence=0.85,
        )
        result = verify_answer(a, q)
        assert result.status == "auto_approved"
        assert result.risk_flags == []

    def test_legal_absolute_in_draft_flagged(self):
        q = Question(id="test", text="General question", category="technical")
        a = Answer(
            question_id="test",
            question_text="General question",
            draft="We guarantee zero breaches at all times.",
            evidence=["doc.md#section"],
            confidence=0.90,
        )
        result = verify_answer(a, q)
        assert any("[LEGAL_RISK]" in f for f in result.risk_flags)

    def test_geographic_keywords_in_question_flagged(self):
        q = Question(id="test", text="Which country is data stored in?", category="data-privacy")
        a = Answer(
            question_id="test",
            question_text="Which country is data stored in?",
            draft="Data is stored in the US.",
            evidence=["storage.md#regions"],
            confidence=0.80,
        )
        result = verify_answer(a, q)
        assert any("[DATA_RESIDENCY]" in f for f in result.risk_flags)


# ============================================================================
# Researcher grounding tests
# ============================================================================

class TestResearcherGrounding:
    def test_off_topic_returns_no_evidence(self):
        q = Question(id="test", text="What is the meaning of life?", category="general")
        a = research_answer(q)
        assert a.confidence == 0.0
        assert a.evidence == []

    def test_encryption_question_finds_evidence(self):
        q = Question(id="test", text="Do you encrypt data at rest?", category="technical")
        a = research_answer(q)
        assert len(a.evidence) > 0
        assert a.confidence > 0.5

    def test_hipaa_question_still_finds_document(self):
        q = Question(id="test", text="Are you HIPAA certified?", category="certification")
        a = research_answer(q)
        # Should find the compliance doc even though Acme is NOT HIPAA certified
        assert len(a.evidence) > 0


# ============================================================================
# Demo data integrity
# ============================================================================

class TestDemoData:
    def test_demo_questions_loaded(self):
        from samples.demo_data import DEMO_QUESTIONS
        assert len(DEMO_QUESTIONS) == 27
        categories = {q.category for q in DEMO_QUESTIONS}
        assert "technical" in categories
        assert "certification" in categories
        assert "data-privacy" in categories
        assert "legal" in categories
        assert "general" in categories

    def test_demo_answers_match_questions(self):
        from samples.demo_data import DEMO_QUESTIONS, DEMO_ANSWERS
        q_ids = {q.id for q in DEMO_QUESTIONS}
        a_ids = {a.question_id for a in DEMO_ANSWERS}
        assert q_ids == a_ids

    def test_demo_review_queue_matches(self):
        from samples.demo_data import DEMO_ANSWERS, DEMO_REVIEW_QUEUE
        expected = [a.question_id for a in DEMO_ANSWERS if a.status == "needs_review"]
        assert DEMO_REVIEW_QUEUE == expected

    def test_demo_has_both_auto_and_review(self):
        from samples.demo_data import DEMO_ANSWERS
        statuses = {a.status for a in DEMO_ANSWERS}
        assert "auto_approved" in statuses
        assert "needs_review" in statuses


# ============================================================================
# Export and action generation
# ============================================================================

class TestExports:
    def test_export_workbook_creates_file(self, tmp_path):
        from samples.demo_data import DEMO_ANSWERS
        path = export_workbook(DEMO_ANSWERS, out_dir=tmp_path, filename="test.xlsx")
        assert path.exists()
        assert path.suffix == ".xlsx"

    def test_summarize_run(self):
        from samples.demo_data import DEMO_ANSWERS
        s = summarize_run(DEMO_ANSWERS)
        assert s.total == 27
        assert s.auto_approved > 0
        assert s.needs_review > 0

    def test_email_draft_contains_stats(self):
        from samples.demo_data import DEMO_ANSWERS
        email = draft_prospect_email(DEMO_ANSWERS)
        assert "Acme SaaS" in email
        assert "27" in email  # total questions
        assert "Subject:" in email

    def test_slack_notification_contains_stats(self):
        from samples.demo_data import DEMO_ANSWERS
        slack = build_slack_notification(DEMO_ANSWERS)
        assert "TrustLoop" in slack
        assert "27" in slack
        assert "Auto-Approved" in slack


# ============================================================================
# End-to-end pipeline
# ============================================================================

class TestEndToEnd:
    def test_full_pipeline_populates_state(self):
        raw = "\n".join([
            "Do you encrypt data at rest?",
            "Are you HIPAA certified?",
            "Where is customer data stored?",
            "What is your favorite color?",
            "Do you guarantee zero breaches?",
        ])
        state = run_pipeline(raw)
        assert len(state["answers"]) == 5
        statuses = [a.status for a in state["answers"]]
        assert statuses.count("auto_approved") == 1
        assert statuses.count("needs_review") == 4
        assert state["final_status"] == "reviewing"

    def test_pipeline_handles_single_question(self):
        state = run_pipeline("Do you encrypt data at rest?")
        assert len(state["answers"]) == 1
        assert state["answers"][0].status == "auto_approved"

    def test_pipeline_all_auto_approve_when_all_technical(self):
        raw = "\n".join([
            "Do you encrypt data at rest?",
            "Do you encrypt data in transit?",
            "What is your MFA policy?",
        ])
        state = run_pipeline(raw)
        assert len(state["answers"]) == 3
        # All should auto-approve (technical questions with strong evidence)
        for a in state["answers"]:
            assert a.status == "auto_approved"
