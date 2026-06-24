r"""LangGraph orchestrator that wires the four-agent state machine.

Flow:
    intake -> research_and_verify -> route -> [final_actions]
                                   \-> [human_review (external)]

Human review is intentionally an EXTERNAL step: the Streamlit UI advances the
queue interactively. The graph is responsible for producing the queue and for
running the final-action node once every item has reached a terminal state.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from agents import parse_questionnaire, research_answer, verify_answer
from models import Answer, GraphState


def _intake_node(state: GraphState) -> dict[str, Any]:
    raw = state.get("raw_input", "")
    questions = parse_questionnaire(raw)
    return {
        "questions": questions,
        "answers": [],
        "review_queue": [],
        "current_review_index": 0,
        "final_status": "processing",
        "actions_taken": [],
    }


def _research_and_verify_node(state: GraphState) -> dict[str, Any]:
    answers: list[Answer] = []
    review_queue: list[str] = []
    for q in state["questions"]:
        drafted = research_answer(q)
        verified = verify_answer(drafted, q)
        answers.append(verified)
        if verified.status == "needs_review":
            review_queue.append(q.id)
    next_status = "reviewing" if review_queue else "completed"
    return {
        "answers": answers,
        "review_queue": review_queue,
        "final_status": next_status,
    }


def build_graph():
    """Construct the compiled LangGraph state machine."""
    graph = StateGraph(GraphState)
    graph.add_node("intake", _intake_node)
    graph.add_node("research_and_verify", _research_and_verify_node)
    graph.set_entry_point("intake")
    graph.add_edge("intake", "research_and_verify")
    graph.add_edge("research_and_verify", END)
    return graph.compile()


def run_pipeline(raw_input: str) -> GraphState:
    """Execute intake + research + verify. Returns full state including queue."""
    app = build_graph()
    initial: GraphState = {"raw_input": raw_input}
    return app.invoke(initial)  # type: ignore[return-value]
