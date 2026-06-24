"""Six-scenario evaluation suite (TC-001 through TC-006).

These exercise the routing precision and zero-hallucination guarantees defined
in the PRD. They run against the deterministic offline path (no API calls)
so CI is reproducible.
"""

from __future__ import annotations

import pytest

from agents import parse_questionnaire, research_answer, verify_answer
from graph import run_pipeline
from models import Answer, Question


def _answer_for(text: str) -> tuple[Question, Answer]:
    questions = parse_questionnaire(text)
    assert questions, f"intake produced no questions for: {text!r}"
    q = questions[0]
    a = research_answer(q)
    a = verify_answer(a, q)
    return q, a


# ---- TC-001: Encryption at rest — should auto-approve with AES-256 + citation. ----

def test_tc001_encryption_at_rest_auto_approves():
    q, a = _answer_for("Do you encrypt data at rest?")
    assert a.status == "auto_approved", a.risk_flags
    assert "AES-256".lower() in a.draft.lower()
    assert any("encryption_policy.md" in cite for cite in a.evidence)
    assert a.confidence >= 0.70


# ---- TC-002: HIPAA certification — must escalate with CERT_WARNING. ----

def test_tc002_hipaa_escalates():
    q, a = _answer_for("Are you HIPAA certified?")
    assert a.status == "needs_review"
    assert any("[CERT_WARNING]" in f for f in a.risk_flags)
    # The grounded draft must NOT claim HIPAA certification.
    assert "is not" in a.draft.lower() or "does not" in a.draft.lower() \
        or "NOT" in a.draft or "no_evidence" in a.draft.lower() \
        or "not hipaa" in a.draft.lower()


# ---- TC-003: Geographic storage — must escalate. ----

def test_tc003_geographic_storage_escalates():
    q, a = _answer_for("Where is customer data stored?")
    assert a.status == "needs_review"
    assert any("[DATA_RESIDENCY]" in f for f in a.risk_flags)


# ---- TC-004: Off-topic question — confidence 0.0, no hallucination. ----

def test_tc004_off_topic_zero_confidence():
    q, a = _answer_for("What is your favorite color?")
    assert a.status == "needs_review"
    assert a.confidence == 0.0
    assert a.evidence == []
    assert any("[MISSING_EVIDENCE]" in f for f in a.risk_flags)


# ---- TC-005: Absolute guarantee — must trigger LEGAL_RISK. ----

def test_tc005_absolute_guarantee_flagged():
    q, a = _answer_for("Do you guarantee zero breaches?")
    assert a.status == "needs_review"
    assert any("[LEGAL_RISK]" in f for f in a.risk_flags)


# ---- TC-006: Malformed / empty input — graceful handling, no crash. ----

def test_tc006_empty_input_does_not_crash():
    state = run_pipeline("")
    assert state["final_status"] in {"completed", "processing", "reviewing"}
    assert state["questions"] == []
    assert state["answers"] == []
    assert state["review_queue"] == []


# ---- Aggregate precision check: 5/5 routing decisions correct. ----

@pytest.mark.parametrize(
    "question_text, expected_status",
    [
        ("Do you encrypt data at rest?", "auto_approved"),
        ("Are you HIPAA certified?", "needs_review"),
        ("Where is customer data stored?", "needs_review"),
        ("What is your favorite color?", "needs_review"),
        ("Do you guarantee zero breaches?", "needs_review"),
    ],
)
def test_routing_precision(question_text: str, expected_status: str):
    _q, a = _answer_for(question_text)
    assert a.status == expected_status


# ---- End-to-end pipeline run sanity check. ----

def test_end_to_end_pipeline_populates_state():
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
    # Exactly one should auto-approve (the encryption question).
    assert statuses.count("auto_approved") == 1
    assert statuses.count("needs_review") == 4
    assert state["final_status"] == "reviewing"
