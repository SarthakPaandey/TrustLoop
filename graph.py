r"""LangGraph orchestrator wiring the full five-stage state machine.

Flow:
    intake -> research_and_verify -> review_gate -[queue empty]-> final_actions -> END
                                              \-[flagged items]-> END (status=reviewing)

Human review is modeled as an explicit GATE inside the graph: when flagged
items exist the graph halts in "reviewing" and control passes to an external
reviewer (Streamlit UI or API caller). Each decision is applied through
``apply_review_decision`` — which also appends to the persistent audit trail —
and ``resume_pipeline`` drives the state through ``final_actions`` once every
item has reached a terminal state. The gate therefore makes HITL a first-class
graph transition instead of an out-of-band side effect.

Research-time memory:
- In-run dedupe: questions that normalize identically share one answer.
- Cross-run reuse: near-identical questions may inherit a previously APPROVED
  answer from storage (similarity >= config.ANSWER_REUSE_SIMILARITY); the
  inherited text is still re-verified against the new question so guardrails
  always run.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langgraph.graph import END, StateGraph

from agents import parse_questionnaire, research_answer, verify_answer
from config import ANSWER_REUSE_SIMILARITY
from models import Answer, GraphState, Question
from storage import db

logger = logging.getLogger(__name__)

_REUSE_NOTE = "Reused previously approved answer"

_NORMALIZE = re.compile(r"[^a-z0-9 ]+")


def _normalize(text: str) -> str:
    collapsed = _NORMALIZE.sub(" ", text.lower())
    return re.sub(r"\s+", " ", collapsed).strip()


def _intake_node(state: GraphState) -> dict[str, Any]:
    raw = state.get("raw_input", "")
    questions = parse_questionnaire(raw)
    run_id = db.create_run(raw)
    return {
        "questions": questions,
        "answers": [],
        "review_queue": [],
        "current_review_index": 0,
        "final_status": "processing",
        "actions_taken": [],
        "run_id": run_id,
    }


def _maybe_reuse(question: Question, seen_norms: dict[str, Answer]) -> Answer | None:
    """Return an inherited answer (in-run duplicate or past-approved), else None.

    Returned candidates are *unverified* — the caller always runs
    ``verify_answer`` so guardrails re-fire for the new question's wording.
    """
    norm = _normalize(question.text)
    if not norm:
        return None

    twin = seen_norms.get(norm)
    if twin is not None:
        return twin.model_copy(
            update={
                "question_id": question.id,
                "question_text": question.text,
                "draft": (
                    f"{twin.draft}\n\n[{_REUSE_NOTE}: duplicate of "
                    f"question {twin.question_id} in this run]"
                ),
            }
        )

    hits = db.find_similar_past_answers(
        question.text, min_similarity=ANSWER_REUSE_SIMILARITY
    )
    if not hits:
        return None
    hit = hits[0]
    source = f"question \"{hit['question_text'][:80]}\""
    return Answer(
        question_id=question.id,
        question_text=question.text,
        draft=f"{hit['answer']}\n\n[{_REUSE_NOTE} for similar {source}]",
        evidence=list(hit.get("evidence") or []),
        confidence=float(hit.get("confidence") or 0.0),
        risk_flags=[],
    )


def _research_and_verify_node(state: GraphState) -> dict[str, Any]:
    answers: list[Answer] = []
    review_queue: list[str] = []
    run_id = state.get("run_id")
    seen_norms: dict[str, Answer] = {}

    for q in state["questions"]:
        inherited = _maybe_reuse(q, seen_norms)
        drafted = inherited if inherited is not None else research_answer(q)
        verified = verify_answer(drafted, q)
        answers.append(verified)
        seen_norms[_normalize(q.text)] = verified
        if verified.status == "needs_review":
            review_queue.append(q.id)

        db.save_answer(
            run_id=run_id,
            question_id=q.id,
            question_text=q.text,
            draft=verified.draft,
            evidence=verified.evidence,
            confidence=verified.confidence,
            risk_flags=verified.risk_flags,
            status=verified.status,
            decided_by=("auto" if verified.status == "auto_approved" else "pipeline"),
        )

    next_status = "reviewing" if review_queue else "completed"
    return {
        "answers": answers,
        "review_queue": review_queue,
        "final_status": next_status,
    }


def _review_gate(state: GraphState) -> str:
    if state.get("review_queue"):
        return "needs_human"
    return "clean"


def _final_actions_node(state: GraphState) -> dict[str, Any]:
    answers: list[Answer] = state.get("answers", [])
    actions: list[str] = []

    try:
        from actions.exporter import export_workbook, summarize_run

        summary = summarize_run(answers)
        workbook = export_workbook(answers)
        actions.append(f"workbook_exported:{workbook.name}")
        actions.append("email_drafted")
        actions.append("slack_notification_built")

        totals = {
            "total": summary.total,
            "auto_approved": summary.auto_approved,
            "human_approved": summary.human_approved,
            "rejected": summary.rejected,
        }
        db.complete_run(state.get("run_id"), "completed", totals)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("final_actions failed: %s", exc)
        actions.append(f"final_actions_error:{exc}")
        db.complete_run(state.get("run_id"), "failed", {"total": len(answers)})

    return {"final_status": "completed", "actions_taken": actions}


def build_graph():
    """Construct the compiled LangGraph state machine."""
    graph = StateGraph(GraphState)
    graph.add_node("intake", _intake_node)
    graph.add_node("research_and_verify", _research_and_verify_node)
    graph.add_node("final_actions", _final_actions_node)
    graph.set_entry_point("intake")
    graph.add_edge("intake", "research_and_verify")
    graph.add_conditional_edges(
        "research_and_verify",
        _review_gate,
        {"needs_human": END, "clean": "final_actions"},
    )
    graph.add_edge("final_actions", END)
    return graph.compile()


def run_pipeline(raw_input: str, persist: bool | None = None) -> GraphState:
    """Execute intake + research + verify (+ delivery when nothing is flagged).

    ``persist=False`` disables storage writes for this invocation (used by
    batch tooling and tests that manage their own fixtures).
    """
    if persist is False:
        with db.disabled():
            app = build_graph()
            return app.invoke({"raw_input": raw_input})  # type: ignore[return-value]
    app = build_graph()
    initial: GraphState = {"raw_input": raw_input}
    return app.invoke(initial)  # type: ignore[return-value]


# ---- Human-in-the-loop continuation ----

def apply_review_decision(
    state: GraphState,
    question_id: str,
    action: str,
    edited_text: str | None = None,
    actor: str = "human_reviewer",
) -> GraphState:
    """Apply one reviewer decision ('approve' | 'edit' | 'reject') to the state.

    Updates the answer record, shrinks the review queue, and persists both the
    decision and an immutable audit event. Mutates and returns ``state``.
    """
    action = action.strip().lower()
    if action not in {"approve", "edit", "reject"}:
        raise ValueError(f"Unknown review action: {action!r}")
    if action == "edit" and not (edited_text or "").strip():
        raise ValueError("Edit action requires non-empty edited_text.")

    answers: list[Answer] = list(state.get("answers", []))
    for i, ans in enumerate(answers):
        if ans.question_id != question_id:
            continue
        final_text = (edited_text or "").strip() or ans.draft
        new_status = "human_approved" if action in {"approve", "edit"} else "rejected"
        updated = ans.model_copy(update={"draft": final_text, "status": new_status})
        answers[i] = updated

        db.record_decision(
            run_id=state.get("run_id"),
            question_id=question_id,
            actor=actor,
            action=f"review_{action}",
            final_text=final_text,
            new_status=new_status,
        )
        break
    else:
        raise KeyError(f"Question {question_id!r} not found in answers")

    queue = [q for q in state.get("review_queue", []) if q != question_id]
    state["answers"] = answers
    state["review_queue"] = queue
    state["current_review_index"] = 0
    return state


def resume_pipeline(state: GraphState) -> GraphState:
    """Continue a paused run once its review queue is empty.

    Runs the final_actions node inline (artifact generation + persistence) and
    marks the run completed. Raises when flagged items remain.
    """
    if state.get("review_queue"):
        raise ValueError(
            f"Cannot resume: {len(state['review_queue'])} item(s) still need review."
        )
    node_out = _final_actions_node(state)
    state.update(node_out)
    return state
