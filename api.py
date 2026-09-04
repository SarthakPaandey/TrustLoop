"""TrustLoop REST API — FastAPI endpoint for programmatic access.

Run with:
    uvicorn api:app --reload --port 8000

Endpoints:
    POST /api/v1/parse          — Parse questionnaire text into structured questions
    POST /api/v1/run            — Run the full pipeline on raw questionnaire text
    POST /api/v1/run/batch      — Run the pipeline over multiple questionnaires
    POST /api/v1/run/decision   — Apply one human review decision to a paused run
    POST /api/v1/run/resume     — Complete a paused run (queue must be empty)
    GET  /api/v1/kb/documents   — List live knowledge-base source files
    POST /api/v1/kb/documents   — Ingest a .md/.txt doc; RAG index rebuilds live
    GET  /api/v1/runs           — Recent persisted runs
    GET  /api/v1/runs/{id}      — Answers for one run (incl. edit history)
    GET  /api/v1/analytics      — Aggregate business metrics across runs
    GET  /api/v1/audit/export   — Immutable audit trail as CSV download
    GET  /api/v1/health         — Health check (no auth)
    GET  /api/v1/stats          — System statistics

Auth: when TRUSTLOOP_API_KEY is set, every endpoint except /health requires an
exact match in the X-API-Key header. Unset = open access (local dev/demo).
"""

from __future__ import annotations

import tempfile

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, ValidationError

from agents import parse_questionnaire
from analytics import compute_analytics
from config import (
    ANSWER_REUSE_SIMILARITY,
    API_AUTH_KEY,
    COMPANY_NAME,
    CONFIDENCE_THRESHOLD,
    LLM_PROVIDER,
    PROSPECT_NAME,
    USE_LLM,
)
from graph import apply_review_decision, resume_pipeline, run_pipeline
from models import Answer, Question
from retrieval import MAX_DOC_CHARS, ingest_document, list_documents
from storage import db

API_VERSION = "2.0.0"

MAX_TEXT_CHARS = 50_000
MAX_BATCH_ITEMS = 25


# ---- Auth ----


async def _guard(x_api_key: str | None = Header(default=None)) -> None:
    """Enforce X-API-Key when TRUSTLOOP_API_KEY is configured."""
    if not API_AUTH_KEY:
        return
    if x_api_key != API_AUTH_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


# ---- Request / Response schemas ----


class ParseRequest(BaseModel):
    text: str = Field(
        description="Raw questionnaire text, one question per line",
        min_length=1,
        max_length=MAX_TEXT_CHARS,
    )


class RunRequest(BaseModel):
    text: str = Field(
        description="Raw questionnaire text, one question per line",
        min_length=1,
        max_length=MAX_TEXT_CHARS,
    )
    persist: bool = Field(default=True, description="Store the run + audit trail")


class BatchRunRequest(BaseModel):
    # NOTE: length cap enforced in the endpoint with 413 (not Pydantic 422)
    # to preserve the documented "Batch limited to 25" contract.
    texts: list[str] = Field(
        description="One questionnaire text per batch item",
        min_length=1,
    )
    persist: bool = Field(default=True)


class StateRequest(BaseModel):
    state: dict = Field(description="A GraphState produced by /run (JSON-safe)")


class ReviewDecisionRequest(StateRequest):
    question_id: str = Field(description="Question being decided", min_length=1)
    action: str = Field(description="approve | edit | reject")
    edited_text: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    actor: str = Field(default="human_reviewer", min_length=1, max_length=100)


class DocumentUploadRequest(BaseModel):
    filename: str = Field(description="Target .md or .txt filename", min_length=1, max_length=128)
    content: str = Field(
        description="UTF-8 document text; index rebuilds immediately",
        min_length=1,
        max_length=MAX_DOC_CHARS,
    )


class DocumentUploadResponse(BaseModel):
    filename: str
    created: bool
    chunks: int
    total_documents: int
    total_chunks: int


class QuestionResponse(BaseModel):
    id: str
    text: str
    category: str


class AnswerResponse(BaseModel):
    question_id: str
    question_text: str
    draft: str
    evidence: list[str]
    confidence: float
    risk_flags: list[str]
    status: str


class RunResponse(BaseModel):
    run_id: str | None
    questions: list[QuestionResponse]
    answers: list[AnswerResponse]
    review_queue: list[str]
    final_status: str
    summary: dict
    state: dict | None = Field(
        default=None, description="Full JSON-safe state for paused runs"
    )
    actions_taken: list[str] | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    company: str
    llm_enabled: bool
    llm_provider: str | None


# ---- App ----

app = FastAPI(
    title="TrustLoop API",
    description="AI-assisted security questionnaire automation",
    version=API_VERSION,
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
        version=API_VERSION,
        company=COMPANY_NAME,
        llm_enabled=USE_LLM,
        llm_provider=LLM_PROVIDER,
    )


@app.post("/api/v1/parse", response_model=list[QuestionResponse],
          dependencies=[Depends(_guard)])
def parse(req: ParseRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    questions = parse_questionnaire(req.text)
    return [
        QuestionResponse(id=q.id, text=q.text, category=q.category)
        for q in questions
    ]


# ---- Helpers ----


def _answer_response(a: Answer) -> AnswerResponse:
    return AnswerResponse(
        question_id=a.question_id,
        question_text=a.question_text,
        draft=a.draft,
        evidence=a.evidence,
        confidence=a.confidence,
        risk_flags=a.risk_flags,
        status=a.status,
    )


def _serialize_state(state: dict) -> dict:
    """GraphState -> JSON-safe dict."""
    out = {k: v for k, v in state.items() if k not in {"questions", "answers"}}
    out["questions"] = [q.model_dump() for q in state.get("questions", [])]
    out["answers"] = [a.model_dump() for a in state.get("answers", [])]
    return out


def _response_from_state(state: dict, include_state: bool | None = None) -> RunResponse:
    answers: list[Answer] = list(state.get("answers", []))
    counts = {"auto_approved": 0, "needs_review": 0,
              "human_approved": 0, "rejected": 0}
    for a in answers:
        counts[a.status] = counts.get(a.status, 0) + 1
    resolved = counts["auto_approved"] + counts["human_approved"]

    paused = bool(state.get("review_queue"))
    if include_state is None:
        include_state = paused
    return RunResponse(
        run_id=state.get("run_id"),
        questions=[
            QuestionResponse(id=q.id, text=q.text, category=q.category)
            for q in state.get("questions", [])
        ],
        answers=[_answer_response(a) for a in answers],
        review_queue=list(state.get("review_queue", [])),
        final_status=state.get("final_status", "unknown"),
        summary={
            "total": len(answers),
            "auto_approved": counts["auto_approved"],
            "needs_review": counts["needs_review"],
            "human_approved": counts["human_approved"],
            "rejected": counts["rejected"],
            "resolved_pct": round(resolved / len(answers) * 100, 1) if answers else 0,
        },
        state=_serialize_state(state) if include_state else None,
        actions_taken=list(state.get("actions_taken", [])) or None,
    )


def _load_state(payload: dict) -> dict:
    state = dict(payload)
    try:
        state["questions"] = [Question(**q) for q in state.get("questions", [])]
        state["answers"] = [Answer(**a) for a in state.get("answers", [])]
    except (ValidationError, TypeError, ValueError, KeyError, AttributeError) as exc:
        raise HTTPException(
            status_code=422, detail=f"Malformed state payload: {exc}"
        ) from exc
    return state


# ---- Pipeline endpoints ----


@app.post("/api/v1/run", response_model=RunResponse, dependencies=[Depends(_guard)])
def run_pipeline_endpoint(req: RunRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    state = run_pipeline(req.text, persist=req.persist)
    return _response_from_state(state)


@app.post("/api/v1/run/batch", response_model=list[RunResponse],
          dependencies=[Depends(_guard)])
def run_batch_endpoint(req: BatchRunRequest):
    if not req.texts:
        raise HTTPException(status_code=400, detail="Batch cannot be empty")
    if len(req.texts) > MAX_BATCH_ITEMS:
        raise HTTPException(
            status_code=413,
            detail=f"Batch limited to {MAX_BATCH_ITEMS} questionnaires",
        )
    for t in req.texts:
        if not t.strip():
            raise HTTPException(status_code=400, detail="Batch items cannot be empty")
        if len(t) > MAX_TEXT_CHARS:
            raise HTTPException(
                status_code=413,
                detail=f"Batch item exceeds {MAX_TEXT_CHARS} characters",
            )
    return [
        _response_from_state(run_pipeline(t, persist=req.persist)) for t in req.texts
    ]


@app.post("/api/v1/run/decision", response_model=RunResponse,
          dependencies=[Depends(_guard)])
def decision_endpoint(decision: ReviewDecisionRequest):
    """Apply one reviewer decision to a paused run; always returns full state
    so callers can chain /resume once the queue is empty."""
    if decision.action.strip().lower() == "edit" and not (decision.edited_text or "").strip():
        raise HTTPException(status_code=422, detail="Edit action requires non-empty edited_text.")
    state = _load_state(decision.state)
    try:
        updated = apply_review_decision(
            state,
            question_id=decision.question_id,
            action=decision.action,
            edited_text=decision.edited_text,
            actor=decision.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _response_from_state(updated, include_state=True)


@app.post("/api/v1/run/resume", response_model=RunResponse,
          dependencies=[Depends(_guard)])
def resume_endpoint(req: StateRequest):
    """Complete a paused run once its review queue is empty."""
    state = _load_state(req.state)
    try:
        completed = resume_pipeline(state)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _response_from_state(completed)


# ---- Live knowledge-base endpoints ----


@app.get("/api/v1/kb/documents", dependencies=[Depends(_guard)])
def kb_list_endpoint():
    """Inventory of KB source files backing the RAG index."""
    return {"documents": list_documents()}


@app.post(
    "/api/v1/kb/documents",
    response_model=DocumentUploadResponse,
    status_code=201,
    dependencies=[Depends(_guard)],
)
def kb_upload_endpoint(req: DocumentUploadRequest):
    """Ingest a .md/.txt document; the RAG index rebuilds immediately."""
    try:
        return ingest_document(req.filename, req.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---- History / analytics endpoints ----


@app.get("/api/v1/runs", dependencies=[Depends(_guard)])
def runs_endpoint(limit: int = Query(default=25, ge=1, le=100)):
    return db.list_runs(limit=limit)


@app.get("/api/v1/runs/{run_id}", dependencies=[Depends(_guard)])
def run_detail_endpoint(run_id: str):
    answers = db.get_run_answers(run_id)
    if not answers:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"run_id": run_id, "answers": answers}


@app.get("/api/v1/analytics", dependencies=[Depends(_guard)])
def analytics_endpoint():
    return compute_analytics(db.analytics_rows())


@app.get("/api/v1/audit/export", dependencies=[Depends(_guard)],
         response_class=PlainTextResponse)
def audit_export_endpoint(run_id: str | None = None):
    # TemporaryDirectory auto-cleans: the old mkstemp version leaked a file
    # descriptor and left CSVs in /tmp on every export.
    with tempfile.TemporaryDirectory(prefix="trustloop_audit_") as tmpdir:
        from pathlib import Path as _Path

        out = _Path(tmpdir) / "trustloop_audit.csv"
        path = db.export_audit_csv(out, run_id=run_id)
        if path is None:
            raise HTTPException(status_code=404, detail="No audit events recorded yet")
        content = path.read_text(encoding="utf-8")
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trustloop_audit.csv"},
    )


@app.get("/api/v1/stats", dependencies=[Depends(_guard)])
def stats():
    return {
        "company": COMPANY_NAME,
        "prospect": PROSPECT_NAME,
        "llm_enabled": USE_LLM,
        "llm_provider": LLM_PROVIDER,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "answer_reuse_similarity": ANSWER_REUSE_SIMILARITY,
        "persistence_enabled": db.enabled(),
        "categories": ["technical", "legal", "certification", "data-privacy", "general"],
        "guardrails": [
            "CERT_WARNING",
            "LEGAL_RISK",
            "DATA_RESIDENCY",
            "MISSING_EVIDENCE",
            "LOW_CONFIDENCE",
            "UNSUPPORTED_CLAIM",
            "ROUTING",
        ],
    }
