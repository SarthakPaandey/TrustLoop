"""Pydantic data models and the LangGraph state channel for TrustLoop."""

from __future__ import annotations

from typing import List, Literal, TypedDict

from pydantic import BaseModel, Field

QuestionCategory = Literal[
    "technical",
    "legal",
    "certification",
    "data-privacy",
    "general",
]

AnswerStatus = Literal[
    "auto_approved",
    "needs_review",
    "human_approved",
    "rejected",
]

FinalStatus = Literal["processing", "reviewing", "completed", "failed"]


class Question(BaseModel):
    id: str = Field(description="Unique identifier for the parsed question")
    text: str = Field(description="The raw text of the question")
    category: QuestionCategory = Field(
        description="Classified category used to route compliance heuristics"
    )


class Answer(BaseModel):
    question_id: str
    question_text: str
    draft: str = Field(description="The generated or edited answer text")
    evidence: List[str] = Field(
        default_factory=list,
        description="List of document chunk references or filenames cited",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score where C in [0.0, 1.0]",
    )
    risk_flags: List[str] = Field(
        default_factory=list,
        description="Text warnings explaining triggered compliance guardrails",
    )
    status: AnswerStatus = "needs_review"


class GraphState(TypedDict, total=False):
    raw_input: str
    questions: List[Question]
    answers: List[Answer]
    review_queue: List[str]
    current_review_index: int
    final_status: FinalStatus
    actions_taken: List[str]
