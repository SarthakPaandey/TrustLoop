# TrustLoop

**AI-assisted security questionnaire automation for B2B SaaS vendors.**

TrustLoop is a multi-agent AI system that parses inbound security questionnaires, retrieves grounded evidence from an approved knowledge base, runs compliance guardrails, and routes risky or uncertain answers to a human reviewer — all before generating any sales-facing artifact.

## The Problem

Enterprise sales cycles stall because:
- **Sales engineers** lack the technical security knowledge to answer questionnaires
- **Security/compliance teams** are bottlenecked by repetitive manual reviews
- **Off-the-shelf LLMs** hallucinate certifications, SLAs, and security claims

## The Solution

TrustLoop combines:
- **RAG (Retrieval-Augmented Generation)** — answers are grounded in verified policy documents, never invented
- **LangGraph state machine** — deterministic agentic workflow with typed state channels
- **Compliance guardrails** — regex + semantic validation catches risky claims before they reach prospects
- **Human-in-the-loop** — uncertain items route to a reviewer with full audit trail

## Architecture

```
[Raw Questionnaire Upload (.xlsx / .txt)]
                 │
                 ▼
   ┌────────────────────────┐
   │ Intake & Parser        │  ← splits, classifies into 5 categories
   └────────────────────────┘
                 │
                 ▼
   ┌──────────────────────────────┐
   │ Researcher & Answerer        │  ← hybrid BM25+TF-IDF RAG over Acme KB
   │ + dedupe / past-answer reuse │     (+ optional OpenAI/Groq)
   └──────────────────────────────┘
                 │
                 ▼
   ┌──────────────────────────────┐
   │ Compliance Verifier          │  ← regex routing + claim-level grounding audit
   └──────────────────────────────┘
         │              │
[C ≥ 0.70 & safe?]  [risky / low C?]
         │              │
         ▼              ▼
   auto_approved   human_review queue (graph review_gate halts here)
         │              │
         └──────┬───────┘
                ▼
   ┌────────────────────────┐
   │ Final Actions          │  ← xlsx export + email + Slack (+ webhook delivery)
   └────────────────────────┘
                │
                ▼
   ┌────────────────────────┐
   │ SQLite persistence     │  ← runs, decisions, immutable audit trail,
   │ + Analytics engine     │     per-run & cross-run metrics
   └────────────────────────┘
```

Every decision made in the review UI or via the API is appended to an
append-only `audit_events` table with actor + timestamp — exportable as CSV
for compliance reviews.

### What's new in v2

- **Hybrid retrieval** — BM25 fused with TF-IDF (`retrieval/vector_store.py`), no extra dependencies.
- **Calibrated confidence** — relevance→confidence interpolation replaces hand-tuned buckets (`agents/researcher.py`).
- **Claim-level grounding audit** — every factual sentence in unanchored drafts must trace to cited evidence or it raises `[UNSUPPORTED_CLAIM]` (`agents/verifier.py`).
- **Negation-aware certification checks** — quoting the "certifications NOT held" policy no longer falsely routes (fixed the SOC 2 false positive).
- **HITL inside the graph** — `review_gate` node halts flagged runs; `apply_review_decision` + `resume_pipeline` drive completion (`graph.py`).
- **Persistence & audit trail** — SQLite via stdlib `sqlite3`, graceful degradation everywhere (`storage/db.py`).
- **Answer memory** — in-run dedupe + cross-run reuse of previously approved answers, always re-verified before acceptance (`graph.py`).
- **Analytics engine** — resolution-rate trend, guardrail frequency, confidence by category, human edit rate (`analytics.py` + new dashboard tabs).
- **API v2** — batch runs, review-decision/resume endpoints, run history, analytics, audit CSV export, optional `X-API-Key` auth.
- **Real Slack delivery** — incoming-webhook support alongside the mockup preview.
- **CI + Dockerfile** — GitHub Actions (pytest + ruff) and a production API image.

## Quick Start

```bash
# Clone and setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# (optional) enable LLM-augmented answer composition
cp .env.example .env
# edit .env and set OPENAI_API_KEY or GROQ_API_KEY

# Run the Streamlit UI
streamlit run app.py

# Or run the API server
uvicorn api:app --reload --port 8000
```

## Demo Script (YC Presentation)

### Option 1: Instant Demo (30 seconds)
1. Run `streamlit run app.py`
2. Click **"Load Demo"** in the sidebar
3. The full 27-question questionnaire loads with pre-computed answers
4. Navigate the review queue to show human-in-the-loop workflow
5. Visit Artifact Hub to show export, email, and Slack notification

### Option 2: Live Pipeline (2 minutes)
1. Run `streamlit run app.py`
2. Click **"Load sample questionnaire"** in the sidebar
3. Click **"Parse questions"** — show the categorized question table
4. Click **"Run multi-agent pipeline"** — watch the animated pipeline visualization
5. In the Review tab:
   - Show auto-approved items (high confidence, clean evidence)
   - Review a flagged HIPAA question (CERT_WARNING)
   - Review a geographic storage question (DATA_RESIDENCY)
   - Show the confidence gauge and risk flags
6. Approve items to clear the queue
7. Artifact Hub: download the workbook, show the email draft and Slack notification

### Option 3: API Demo (1 minute)
```bash
# Start the API
uvicorn api:app --reload --port 8000

# Parse a questionnaire
curl -X POST http://localhost:8000/api/v1/parse \
  -H "Content-Type: application/json" \
  -d '{"text": "Do you encrypt data at rest?\nAre you HIPAA certified?"}'

# Run the full pipeline
curl -X POST http://localhost:8000/api/v1/run \
  -H "Content-Type: application/json" \
  -d '{"text": "Do you encrypt data at rest?\nAre you HIPAA certified?"}'
```

## Safety Matrix

| Trigger | Action | Flag |
|---------|--------|------|
| Confidence < 0.70 | Route to human | `[LOW_CONFIDENCE]` |
| Mentions HIPAA / PCI-DSS / FedRAMP in question (or unqualified in draft) | Route to human | `[CERT_WARNING]` |
| Absolute legal language | Route to human | `[LEGAL_RISK]` |
| Geographic / residency question | Route to human | `[DATA_RESIDENCY]` |
| Empty evidence after retrieval | Route to human | `[MISSING_EVIDENCE]` |
| Sentence not traceable to cited evidence | Route to human | `[UNSUPPORTED_CLAIM]` |
| Category = `legal` | Route to human | `[ROUTING]` |
| Insurance-related question | Route to human | `[ROUTING]` |

Certification mentions inside an explicitly negative sentence ("Acme SaaS is
NOT HIPAA certified") are treated as grounded negatives and do **not**
escalate — otherwise quoting the certifications-not-held policy would route
every honest answer to review.

## Key Metrics

| Metric | Target | Status |
|--------|--------|--------|
| Zero Hallucination Escape Rate | 0% | Verified by 76 integration tests (incl. claim-level grounding audit) |
| Safe Automation Rate | ≥ 40% | ~55% of questions auto-approve |
| Routing Precision | 100% | All flagged items correctly routed |

## Project Layout

```
.
├── app.py                    # Streamlit UI (landing + 6-view workspace)
├── api.py                    # FastAPI REST API v2 (auth, batch, review, audit)
├── graph.py                  # LangGraph orchestrator (intake → verify → gate → actions)
├── models.py                 # Pydantic schemas + GraphState
├── analytics.py              # Metrics engine over stored runs
├── config.py                 # Env + thresholds + integration settings
├── agents/
│   ├── intake.py             # Parser & classifier (5 categories)
│   ├── researcher.py         # RAG answerer + calibrated confidence
│   └── verifier.py           # Routing heuristics + claim-level grounding audit
├── retrieval/
│   └── vector_store.py       # Hybrid BM25 + TF-IDF with score fusion
├── storage/
│   └── db.py                 # SQLite persistence, audit trail, answer memory
├── actions/
│   ├── exporter.py           # openpyxl xlsx export
│   ├── email_drafter.py      # Prospect email
│   ├── auto_email.py         # SMTP sender with pre-flight checks
│   └── slack_notifier.py     # Slack block builder + webhook delivery
├── kb/                       # Acme SaaS policy documents (10 docs)
├── samples/                  # Demo data + sample questionnaires
├── tests/
│   ├── conftest.py           # Isolated test DB
│   ├── test_evaluation.py    # Original 38 tests
│   └── test_upgrades.py     # 38 v2 tests (retrieval, claims, HITL, API…)
├── .github/workflows/ci.yml  # pytest + ruff on every push
├── Dockerfile                # Production API image
└── requirements.txt
```

## Dashboard Views

| View | Purpose |
|------|---------|
| 📥 Summary | Parse/run pipeline, category breakdown, question browser |
| 🧪 Review | Guided one-at-a-time review with live diff vs original draft |
| 📦 Deliver | XLSX export, email preview, Slack preview + real webhook send |
| 📊 Analytics | Resolution-rate trend, guardrail frequency, confidence by category, edit rate |
| 🛡️ Audit | Per-run decision log with actor attribution + CSV export |
| 📚 Knowledge Base | Source document browser |

## Operating Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| Deterministic offline | No API key set | Hybrid retrieval + template composition. Fully reproducible. |
| LLM-augmented | `OPENAI_API_KEY` or `GROQ_API_KEY` set | Same retrieval; LLM composes final wording from retrieved chunks, then passes the claim-level grounding audit. |

Both modes share the same retrieval layer and compliance verifier, so the zero-hallucination guarantee holds in either configuration.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check (no auth) |
| `/api/v1/parse` | POST | Parse questionnaire text into structured questions |
| `/api/v1/run` | POST | Run the full pipeline; paused runs return resumable state |
| `/api/v1/run/batch` | POST | Run up to 25 questionnaires in one call |
| `/api/v1/run/decision` | POST | Apply one review decision (approve/edit/reject) to a paused run |
| `/api/v1/run/resume` | POST | Complete a paused run once its queue is empty |
| `/api/v1/kb/documents` | GET | List live knowledge-base source files |
| `/api/v1/kb/documents` | POST | Ingest a `.md`/`.txt` doc; RAG index rebuilds live |
| `/api/v1/runs` | GET | Recent persisted runs |
| `/api/v1/runs/{id}` | GET | Full answer record for one run (incl. edit history) |
| `/api/v1/analytics` | GET | Aggregate metrics across stored runs |
| `/api/v1/audit/export` | GET | Immutable audit trail as CSV download |
| `/api/v1/stats` | GET | System statistics and guardrail info |

### Live documents

The RAG index is no longer frozen at startup. Drop a `.md`/`.txt` file into
the Knowledge Base tab (or `POST` it to `/api/v1/kb/documents`) and the index
rebuilds immediately — the next pipeline run can cite the new document, and
the verifier's grounding audit applies to it like any built-in policy.

```bash
curl -X POST http://localhost:8000/api/v1/kb/documents \
  -H "Content-Type: application/json" \
  -d '{"filename": "vpn_policy.md", "content": "# VPN Policy\n\nAll remote access must use WireGuard VPN."}'
```

Limits: UTF-8 `.md`/`.txt` only, 200k characters per doc, 200 docs max.
Filenames are sanitized (no path traversal; re-uploading a name updates it).
On ephemeral hosts (Streamlit Community Cloud) uploaded docs live until the
next redeploy — commit long-lived policies to `kb/` in git.

**Auth:** set `TRUSTLOOP_API_KEY` and clients must send it as the `X-API-Key`
header on every endpoint except `/health`. Unset means open access (local dev
/ demo).

```bash
curl -X POST http://localhost:8000/api/v1/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $TRUSTLOOP_API_KEY" \
  -d '{"text": "Do you encrypt data at rest?"}'
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` / `GROQ_API_KEY` | Optional LLM-augmented answer composition |
| `TRUSTLOOP_API_KEY` | Enables X-API-Key auth on the REST API |
| `SLACK_WEBHOOK_URL` | Enables real Slack delivery from the Deliver tab |
| `TRUSTLOOP_DB_PATH` | SQLite location (default `data/trustloop.db`) |
| `TRUSTLOOP_DISABLE_DB=1` | Run fully in-memory (no persistence) |

## Tech Stack

- **Orchestration**: LangGraph (state machine)
- **Retrieval**: TF-IDF + cosine similarity (scikit-learn)
- **LLM**: OpenAI GPT-4o-mini / Groq Llama 3.3 (optional)
- **UI**: Streamlit with custom CSS
- **API**: FastAPI
- **Data**: Pydantic v2, openpyxl
- **Testing**: pytest (38 tests)

## Deploy (Streamlit Community Cloud)

1. Push this repo to GitHub (public repo works on the free tier).
2. Open [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. **New app** → select `SarthakPaandey/TrustLoop` (or your fork) → branch `main` → main file `app.py`.
4. In **Advanced settings**, set **Python version to 3.12** (or 3.11).  
   Community Cloud ignores `runtime.txt` — the version must be chosen in the UI.  
   If the app is already deployed on 3.14 and misbehaves: delete the app and redeploy with 3.12.
5. (Optional) **Advanced settings → Secrets** — paste:

```toml
OPENAI_API_KEY = "sk-..."
OPENAI_MODEL = "gpt-4o-mini"
```

Or use Groq:

```toml
GROQ_API_KEY = "gsk_..."
GROQ_MODEL = "llama-3.3-70b-versatile"
```

Without secrets the app runs fully offline (TF-IDF + templates).

6. Click **Deploy**. URL will look like `https://<app-name>.streamlit.app`.

## Deploy (Docker / API server)

```bash
docker build -t trustloop-api .
docker run -p 8000:8000 \
  -e TRUSTLOOP_API_KEY=change-me \
  -e SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... \
  trustloop-api
```

## CI

GitHub Actions runs `ruff` and the full 76-test suite on every push to `main`
and on all pull requests (`.github/workflows/ci.yml`).

## License

MIT
