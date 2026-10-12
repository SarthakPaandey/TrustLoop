"""Quality checks: review priority, contradictions, coverage, secrets, readiness."""

from __future__ import annotations

from pathlib import Path

from models import Answer
from quality.consistency import find_conflicts
from quality.coverage import coverage_gaps
from quality.readiness import assess_readiness
from quality.sensitive import redact_answers, scan_answers
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


class TestContradictions:
    def test_encryption_yes_and_no_conflict(self):
        answers = [
            _ans(
                "Q-yes",
                "Do you encrypt data at rest?",
                "Yes. Customer data is encrypted at rest with AES-256.",
                status="auto_approved",
                confidence=0.92,
                evidence=["encryption_policy.md"],
            ),
            _ans(
                "Q-no",
                "Is stored data encrypted at rest?",
                "No. Data at rest is not encrypted.",
                status="auto_approved",
                confidence=0.9,
                evidence=["encryption_policy.md"],
            ),
        ]
        conflicts = find_conflicts(answers)
        assert len(conflicts) == 1
        assert conflicts[0]["topic"] == "encryption_at_rest"
        assert conflicts[0]["question_ids"] == ["Q-yes", "Q-no"]

    def test_matching_negatives_are_not_a_conflict(self):
        answers = [
            _ans(
                "Q-a",
                "Are you HIPAA certified?",
                "No. Acme SaaS is NOT HIPAA certified.",
                evidence=["compliance.md"],
            ),
            _ans(
                "Q-b",
                "Do you sign BAAs for HIPAA?",
                "Acme SaaS is NOT HIPAA certified and does not sign BAAs.",
                evidence=["compliance.md"],
            ),
        ]
        assert find_conflicts(answers) == []

    def test_optional_region_is_not_an_exclusive_claim(self):
        answers = [
            _ans(
                "Q-primary",
                "Where is customer data stored?",
                "Primary region is us-east-1. EU data can optionally be hosted in eu-west-1.",
                status="auto_approved",
                evidence=["storage.md"],
            ),
            _ans(
                "Q-dr",
                "Where is the disaster-recovery copy stored?",
                "Warm standby is in us-west-2.",
                status="auto_approved",
                evidence=["storage.md"],
            ),
        ]
        assert find_conflicts(answers) == []

    def test_exclusive_regions_conflict(self):
        answers = [
            _ans(
                "Q-us",
                "Where is customer data stored?",
                "Customer data is stored only in the United States.",
                status="auto_approved",
                evidence=["storage.md"],
            ),
            _ans(
                "Q-eu",
                "Where is production data stored?",
                "All production data is stored exclusively in the European Union.",
                status="auto_approved",
                evidence=["storage.md"],
            ),
        ]
        conflicts = find_conflicts(answers)
        assert len(conflicts) == 1
        assert conflicts[0]["topic"] == "data_residency"

    def test_retention_windows_must_differ_sharply(self):
        close = [
            _ans(
                "Q-a",
                "How long is customer data retained?",
                "Data is retained for 30 days after termination.",
                status="auto_approved",
                evidence=["storage.md"],
            ),
            _ans(
                "Q-b",
                "What is backup retention?",
                "Backups are retained for 35 days.",
                status="auto_approved",
                evidence=["storage.md"],
            ),
        ]
        assert find_conflicts(close) == []
        far = [
            close[0],
            _ans(
                "Q-c",
                "What is log retention?",
                "Logs are retained for 365 days.",
                status="auto_approved",
                evidence=["storage.md"],
            ),
        ]
        topics = [item["topic"] for item in find_conflicts(far)]
        assert topics == ["retention"]


class TestCoverageAndSecrets:
    def test_missing_evidence_suggests_a_policy(self):
        gaps = coverage_gaps([
            _ans(
                "Q-h",
                "Are you HIPAA certified?",
                "No.",
                flags=["[MISSING_EVIDENCE] no source"],
            )
        ])
        assert gaps[0]["reasons"] == ["missing_evidence", "no_citations"]
        assert "PHI" in gaps[0]["suggestion"]

    def test_cited_answer_is_not_a_gap(self):
        gaps = coverage_gaps([
            _ans(
                "Q-e",
                "Do you encrypt data at rest?",
                "AES-256 encryption at rest.",
                status="auto_approved",
                evidence=["encryption_policy.md"],
                confidence=0.9,
            )
        ])
        assert gaps == []

    def test_secret_is_redacted_and_blocks_send(self):
        key = "AKIA" + ("A" * 16)
        original = _ans(
            "Q-key",
            "How are keys stored?",
            f"Inline key {key} was pasted by mistake.",
            status="auto_approved",
            evidence=["kms.md"],
            confidence=0.9,
        )
        hits = scan_answers([original])
        assert hits[0]["kind"] == "aws_access_key"
        assert key not in hits[0]["excerpt"]
        assert "[REDACTED]" in hits[0]["excerpt"]
        redacted = redact_answers([original])
        assert key not in redacted[0].draft
        assert key in original.draft
        report = assess_readiness([original])
        assert report["ready_to_send"] is False
        assert report["score"] == 75

    def test_private_ip_warns_without_blocking(self):
        answer = _ans(
            "Q-net",
            "Which management network do you use?",
            "The jump host is 10.1.2.3.",
            status="human_approved",
            evidence=["network.md"],
            confidence=0.8,
        )
        report = assess_readiness([answer])
        assert report["ready_to_send"] is True
        assert report["counts"]["sensitive"] == 1
        assert report["score"] == 96

    def test_rejected_draft_is_not_scanned(self):
        key = "AKIA" + ("B" * 16)
        answer = _ans(
            "Q-rej",
            "Keys?",
            f"Rejected draft still mentions {key}.",
            status="rejected",
            evidence=["kms.md"],
        )
        assert scan_answers([answer]) == []


class TestReadiness:
    def test_empty_packet_is_ready(self):
        report = assess_readiness([])
        assert report["score"] == 100
        assert report["ready_to_send"] is True

    def test_open_review_and_thin_evidence_both_count(self):
        report = assess_readiness([
            _ans(
                "Q-open",
                "What is your favorite color?",
                "Not in the knowledge base.",
                flags=["[MISSING_EVIDENCE] none", "[LOW_CONFIDENCE] low"],
                confidence=0.1,
            )
        ])
        assert report["ready_to_send"] is False
        assert report["counts"]["open_review"] == 1
        assert report["counts"]["coverage_gaps"] == 1
        # 8 for the open item, 4 for the coverage warning.
        assert report["score"] == 88

    def test_rejection_blocks_even_with_evidence(self):
        report = assess_readiness([
            _ans(
                "Q-no",
                "Do you encrypt data at rest?",
                "AES-256 encryption at rest.",
                status="rejected",
                evidence=["encryption_policy.md"],
                confidence=0.9,
            )
        ])
        assert report["ready_to_send"] is False
        assert report["score"] == 85

    def test_demo_and_sample_do_not_invent_contradictions(self):
        from graph import run_pipeline
        from samples.demo_data import DEMO_ANSWERS

        assert find_conflicts(DEMO_ANSWERS) == []
        sample = Path("samples/sample_questionnaire.txt").read_text(encoding="utf-8")
        state = run_pipeline(sample, persist=False)
        assert find_conflicts(state["answers"]) == []
