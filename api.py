"""TrustLoop REST API — FastAPI endpoint for programmatic access.

Run with:
    uvicorn api:app --reload --port 8000

Provides:
    POST /api/v1/parse      — Parse questionnaire text into structured questions
    POST /api/v1/run        — Run the full pipeline on raw questionnaire text
    GET  /api/v1/health     — Health check
    GET  /api/v1/stats      — System statistics
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents import parse_questionnaire
from config import COMPANY_NAME, PROSPECT_NAME, USE_LLM, LLM_PROVIDER
from graph import run_pipeline
from models import Answer, Question


# ---- Request / Response schemas ----

class ParseRequest(BaseModel):
    text: str = Field(description="Raw questionnaire text, one question per line")
    
class RunRequest(BaseModel):
    text: str = Field(description="Raw questionnaire text, one question per line")

class QuestionResponse(BaseModel):
    id: str
    text: str
    category: str

class AnswerResponse(BaseModel):
    question_id: str
    question_text: str
    draft: str
    evidence: List[str]
    confidence: float
    risk_flags: List[str]
    status: str

class RunResponse(BaseModel):
    questions: List[QuestionResponse]
    answers: List[AnswerResponse]
    review_queue: List[str]
    final_status: str
    summary: dict

class HealthResponse(BaseModel):
    status: str
    version: str
    company: str
    llm_enabled: bool
    llm_provider: Optional[str]


# ---- App ----

app = FastAPI(
    title="TrustLoop API",
    description="AI-assisted security questionnaire automation",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        company=COMPANY_NAME,
        llm_enabled=USE_LLM,
        llm_provider=LLM_PROVIDER,
    )


@app.post("/api/v1/parse", response_model=List[QuestionResponse])
def parse(req: ParseRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    questions = parse_questionnaire(req.text)
    return [
        QuestionResponse(id=q.id, text=q.text, category=q.category)
        for q in questions
    ]


@app.post("/api/v1/run", response_model=RunResponse)
def run_pipeline_endpoint(req: RunRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    state = run_pipeline(req.text)
    
    answers = list(state.get("answers", []))
    auto = sum(1 for a in answers if a.status == "auto_approved")
    review = sum(1 for a in answers if a.status == "needs_review")
    approved = sum(1 for a in answers if a.status == "human_approved")
    rejected = sum(1 for a in answers if a.status == "rejected")
    
    return RunResponse(
        questions=[
            QuestionResponse(id=q.id, text=q.text, category=q.category)
            for q in state.get("questions", [])
        ],
        answers=[
            AnswerResponse(
                question_id=a.question_id,
                question_text=a.question_text,
                draft=a.draft,
                evidence=a.evidence,
                confidence=a.confidence,
                risk_flags=a.risk_flags,
                status=a.status,
            )
            for a in answers
        ],
        review_queue=state.get("review_queue", []),
        final_status=state.get("final_status", "unknown"),
        summary={
            "total": len(answers),
            "auto_approved": auto,
            "needs_review": review,
            "human_approved": approved,
            "rejected": rejected,
            "auto_pct": round(auto / len(answers) * 100, 1) if answers else 0,
        },
    )


@app.get("/api/v1/stats")
def stats():
    return {
        "company": COMPANY_NAME,
        "prospect": PROSPECT_NAME,
        "llm_enabled": USE_LLM,
        "llm_provider": LLM_PROVIDER,
        "confidence_threshold": 0.70,
        "categories": ["technical", "legal", "certification", "data-privacy", "general"],
        "guardrails": [
            "CERT_WARNING",
            "LEGAL_RISK",
            "DATA_RESIDENCY",
            "MISSING_EVIDENCE",
            "LOW_CONFIDENCE",
            "ROUTING",
        ],
    }
