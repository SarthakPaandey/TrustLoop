"""Quality checks: review priority, contradictions, coverage, secrets, readiness."""

from __future__ import annotations

from models import Answer
from quality.triage import explain_priority, prioritize_review_queue, risk_score


def _ans(
    qid: str,
    text: str,
    draft: str,
    status: str = "needs_review",
    flags: list[str] | None = None,
    confidence: float = 0.5,
    evidence: list[str] | None = None,
) -> Answer:
    return Answer(
        question_id=qid,
        question_text=text,
        draft=draft,
        evidence=evidence or [],
        confidence=confidence,
        risk_flags=flags or [],
        status=status,
    )


class TestReviewPriority:
    def test_certification_outranks_low_confidence(self):
        answers = [
            _ans(
                "Q-low",
                "What is your favorite color?",
                "Unknown.",
                flags=["[LOW_CONFIDENCE] below threshold"],
                confidence=0.1,
            ),
            _ans(
                "Q-cert",
                "Are you HIPAA certified?",
                "No. Acme SaaS is NOT HIPAA certified.",
                flags=["[CERT_WARNING] not held"],
                confidence=0.9,
            ),
        ]
        assert prioritize_review_queue(answers) == ["Q-cert", "Q-low"]

    def test_skips_approved_and_keeps_ties_stable(self):
        answers = [
            _ans("Q-ok", "Encrypt?", "Yes.", status="auto_approved", confidence=0.95),
            _ans(
                "Q-a",
                "PCI?",
                "Not PCI certified.",
                flags=["[CERT_WARNING] pci"],
                confidence=0.8,
            ),
            _ans(
                "Q-b",
                "FedRAMP?",
                "Not FedRAMP authorized.",
                flags=["[CERT_WARNING] fedramp"],
                confidence=0.8,
            ),
        ]
        # Same severity and confidence: original order wins.
        assert prioritize_review_queue(answers) == ["Q-a", "Q-b"]
        assert risk_score(answers[0]) == 0

    def test_lower_confidence_breaks_a_severity_tie(self):
        answers = [
            _ans("Q-sure", "A?", "No.", flags=["[LEGAL_RISK] x"], confidence=0.8),
            _ans("Q-unsure", "B?", "No.", flags=["[LEGAL_RISK] x"], confidence=0.4),
        ]
        assert prioritize_review_queue(answers) == ["Q-unsure", "Q-sure"]

    def test_explain_priority_names_the_strongest_flag(self):
        answer = _ans(
            "Q-1",
            "HIPAA?",
            "No.",
            flags=["[LOW_CONFIDENCE] low", "[CERT_WARNING] hipaa"],
        )
        text = explain_priority(answer)
        assert text.startswith("High priority")
        assert "certification warning" in text

    def test_pipeline_queue_is_risk_ordered(self):
        from graph import run_pipeline

        state = run_pipeline(
            "What is your favorite color?\nAre you HIPAA certified?",
            persist=False,
        )
        assert state["final_status"] == "reviewing"
        by_id = {a.question_id: a for a in state["answers"]}
        queue = state["review_queue"]
        assert len(queue) == 2
        assert any("CERT_WARNING" in flag for flag in by_id[queue[0]].risk_flags)
        assert "favorite color" in by_id[queue[1]].question_text.lower()
