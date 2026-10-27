"""TrustLoop REST API — FastAPI endpoint for programmatic access.

Run with:
    uvicorn api:app --reload --port 8000

Endpoints:
    POST /api/v1/parse          — Parse questionnaire text into structured questions
    POST /api/v1/run            — Run the full pipeline on raw questionnaire text
    POST /api/v1/run/batch      — Run the pipeline over multiple questionnaires
    POST /api/v1/run/decision   — Apply one human review decision to a paused run
    POST /api/v1/run/resume     — Complete a paused run (queue must be empty)
    POST /api/v1/quality        — Score contradictions, coverage, secrets, send readiness
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

import contextlib
import tempfile
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    Security,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
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
from quality.readiness import assess_readiness
from retrieval import MAX_DOC_CHARS, ingest_document, list_documents
from storage import db
from transcription import (
    ALL_MEDIA_EXTS,
    transcribe_media,
)

API_VERSION = "2.1.0"

MAX_TEXT_CHARS = 50_000
MAX_BATCH_ITEMS = 25

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


# ---- Auth ----


async def _guard(
    x_api_key: str | None = Security(api_key_header),
    auth_cred: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> None:
    """Enforce API key authentication.

    Supports X-API-Key header or Authorization: Bearer <key>.
    Checks TRUSTLOOP_API_KEY env var and active API keys in the database.
    If TRUSTLOOP_API_KEY is configured, valid authentication is mandatory.
    If TRUSTLOOP_API_KEY is unset and a token is provided, it is validated against active keys.
    If TRUSTLOOP_API_KEY is unset and no token is provided, open access is allowed (local dev/demo).
    """
    token = None
    if x_api_key and x_api_key.strip():
        token = x_api_key.strip()
    elif auth_cred and auth_cred.credentials:
        token = auth_cred.credentials.strip()

    # If static master API_AUTH_KEY is configured
    if API_AUTH_KEY:
        if token == API_AUTH_KEY or (token and db.verify_api_key(token)):
            return
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Provide X-API-Key header or Authorization: Bearer <key>.",
        )

    # When API_AUTH_KEY is unset:
    # If caller provided a token, validate it against active DB API keys
    if token:
        if db.verify_api_key(token):
            return
        raise HTTPException(
            status_code=401,
            detail="Invalid or inactive API key.",
        )

    # No token provided and no master API_AUTH_KEY set -> open access (local dev / demo / tests)
    return




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


class QualityAnswer(BaseModel):
    """One answer to score without re-running retrieval."""

    question_id: str = Field(min_length=1, max_length=64)
    question_text: str = Field(min_length=1, max_length=4_000)
    draft: str = Field(default="", max_length=MAX_TEXT_CHARS)
    evidence: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_flags: list[str] = Field(default_factory=list, max_length=20)
    status: str = Field(default="needs_review")


class QualityRequest(BaseModel):
    answers: list[QualityAnswer] = Field(min_length=1, max_length=200)


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
    quality: dict | None = Field(
        default=None,
        description="Send-readiness score plus contradiction, coverage, and secret findings",
    )


class CreateKeyRequest(BaseModel):
    name: str = Field(default="Default Key", min_length=1, max_length=100)
    rate_limit: int = Field(default=100, ge=1, le=10000)


class CreateKeyResponse(BaseModel):
    key_id: str
    name: str
    api_key: str
    key_preview: str
    created_at: str
    rate_limit: int
    is_active: bool


class ApiKeyInfo(BaseModel):
    key_id: str
    name: str
    key_preview: str
    created_at: str
    last_used_at: str | None = None
    is_active: int
    rate_limit: int
    created_by: str | None = None


class VideoTranscribeResponse(BaseModel):
    transcription_id: str | None
    filename: str
    duration_seconds: float
    provider: str
    model: str
    transcript: str
    detected_questions: list[str]


class HealthResponse(BaseModel):
    status: str
    version: str
    company: str
    llm_enabled: bool
    llm_provider: str | None
    database_engine: str


# ---- App ----

app = FastAPI(
    title="TrustLoop API",
    description="AI-assisted security questionnaire automation with video transcription and API key management",
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
        database_engine=db.get_database_engine(),
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
        quality=assess_readiness(answers),
    )


def _quality_answers(items: list[QualityAnswer]) -> list[Answer]:
    try:
        return [
            Answer(
                question_id=item.question_id,
                question_text=item.question_text,
                draft=item.draft,
                evidence=list(item.evidence),
                confidence=item.confidence,
                risk_flags=list(item.risk_flags),
                status=item.status,  # type: ignore[arg-type]
            )
            for item in items
        ]
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Malformed answers: {exc}") from exc


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


@app.post("/api/v1/quality", dependencies=[Depends(_guard)])
def quality_endpoint(req: QualityRequest):
    """Score a set of answers for contradictions, thin evidence, and secrets.

    Does not re-run retrieval. Callers can pass the answers from ``/run`` or
    from a reviewer session that has not been persisted yet.
    """
    return assess_readiness(_quality_answers(req.answers))


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
        "database_engine": db.get_database_engine(),
        "api_keys_active": len([k for k in db.list_api_keys() if k.get("is_active")]),
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


# ---- API Key Management Endpoints ----


@app.post(
    "/api/v1/auth/keys",
    response_model=CreateKeyResponse,
    status_code=201,
    dependencies=[Depends(_guard)],
)
def create_api_key_endpoint(req: CreateKeyRequest):
    """Generate a new developer API key."""
    created = db.create_api_key(name=req.name, rate_limit=req.rate_limit)
    if not created:
        raise HTTPException(status_code=500, detail="Failed to generate API key")
    return CreateKeyResponse(**created)


@app.get(
    "/api/v1/auth/keys",
    response_model=list[ApiKeyInfo],
    dependencies=[Depends(_guard)],
)
def list_api_keys_endpoint():
    """List all API keys with masked previews."""
    return [ApiKeyInfo(**k) for k in db.list_api_keys()]


@app.delete(
    "/api/v1/auth/keys/{key_id}",
    status_code=200,
    dependencies=[Depends(_guard)],
)
def revoke_api_key_endpoint(key_id: str):
    """Revoke an active API key."""
    success = db.revoke_api_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"API key {key_id} not found or already inactive")
    return {"status": "revoked", "key_id": key_id}


# ---- Video & Audio Intake Endpoints ----


@app.post(
    "/api/v1/video/transcribe",
    response_model=VideoTranscribeResponse,
    dependencies=[Depends(_guard)],
)
async def video_transcribe_endpoint(file: UploadFile = File(...)):
    """Upload a video or audio file to extract audio and transcribe dialogue into text."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename missing")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALL_MEDIA_EXTS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported media format '{suffix}'. Supported: {', '.join(sorted(ALL_MEDIA_EXTS))}",
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        res = transcribe_media(tmp_path)
        t_id = db.save_transcription(
            filename=file.filename,
            transcript_text=res["text"],
            detected_questions=res["detected_questions"],
            duration_seconds=res["duration_seconds"],
        )
        return VideoTranscribeResponse(
            transcription_id=t_id,
            filename=file.filename,
            duration_seconds=res["duration_seconds"],
            provider=res["provider"],
            model=res["model"],
            transcript=res["text"],
            detected_questions=res["detected_questions"],
        )
    finally:
        with contextlib.suppress(OSError):
            tmp_path.unlink()


@app.post(
    "/api/v1/video/run",
    response_model=RunResponse,
    dependencies=[Depends(_guard)],
)
async def video_run_pipeline_endpoint(
    file: UploadFile = File(...),
    persist: bool = Form(default=True),
):
    """Upload a video or audio file: transcribes audio, parses compliance questions,
    and runs the full verification pipeline through the LangGraph engine."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename missing")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALL_MEDIA_EXTS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported media format '{suffix}'. Supported: {', '.join(sorted(ALL_MEDIA_EXTS))}",
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        res = transcribe_media(tmp_path)
        questions_text = "\n".join(res["detected_questions"])
        if not questions_text.strip():
            questions_text = res["text"]

        if not questions_text.strip():
            raise HTTPException(status_code=422, detail="No speech or questions detected in media file")

        state = run_pipeline(questions_text, persist=persist)

        # Link transcription to run in DB
        db.save_transcription(
            filename=file.filename,
            transcript_text=res["text"],
            detected_questions=res["detected_questions"],
            duration_seconds=res["duration_seconds"],
            run_id=state.get("run_id"),
        )
        return _response_from_state(state)
    finally:
        with contextlib.suppress(OSError):
            tmp_path.unlink()


@app.post(
    "/api/v1/kb/video",
    response_model=DocumentUploadResponse,
    status_code=201,
    dependencies=[Depends(_guard)],
)
async def kb_video_upload_endpoint(
    file: UploadFile = File(...),
    doc_name: str | None = Form(default=None),
):
    """Ingest a video or audio briefing/policy into the Knowledge Base.
    Transcribes audio, formats as markdown documentation, and rebuilds the RAG index immediately."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename missing")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALL_MEDIA_EXTS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported media format '{suffix}'. Supported: {', '.join(sorted(ALL_MEDIA_EXTS))}",
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        res = transcribe_media(tmp_path)
        target_name = doc_name.strip() if doc_name and doc_name.strip() else f"{Path(file.filename).stem}.md"
        if not target_name.endswith(".md") and not target_name.endswith(".txt"):
            target_name = f"{target_name}.md"

        formatted_content = (
            f"# Source: {file.filename}\n\n"
            f"> Transcribed via {res.get('provider', 'speech-engine')} ({res.get('model', 'whisper')})\n\n"
            f"## Spoken Content\n\n"
            f"{res['text']}\n"
        )
        return ingest_document(target_name, formatted_content)
    finally:
        with contextlib.suppress(OSError):
            tmp_path.unlink()


@app.get(
    "/api/v1/video/transcriptions",
    dependencies=[Depends(_guard)],
)
def list_transcriptions_endpoint(limit: int = Query(default=25, ge=1, le=100)):
    """List recent audio and video transcriptions stored in the database."""
    return db.list_transcriptions(limit=limit)

