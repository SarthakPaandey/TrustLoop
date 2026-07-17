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
   ┌────────────────────────┐
   │ Researcher & Answerer  │  ← TF-IDF RAG over Acme SaaS KB
   └────────────────────────┘                (+ optional OpenAI)
                 │
                 ▼
   ┌────────────────────────┐
   │ Compliance Verifier    │  ← regex + confidence + category routing
   └────────────────────────┘
        │              │
[C ≥ 0.70 & safe?]  [risky / low C?]
        │              │
        ▼              ▼
  auto_approved   human_review queue (Streamlit UI)
        │              │
        └──────┬───────┘
               ▼
   ┌────────────────────────┐
   │ Final Actions          │  ← xlsx export + email + Slack
   └────────────────────────┘
```

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
| Mentions HIPAA / PCI-DSS / FedRAMP | Route to human | `[CERT_WARNING]` |
| Absolute legal language | Route to human | `[LEGAL_RISK]` |
| Geographic / residency question | Route to human | `[DATA_RESIDENCY]` |
| Empty evidence after retrieval | Route to human | `[MISSING_EVIDENCE]` |
| Category = `legal` | Route to human | `[ROUTING]` |
| Insurance-related question | Route to human | `[ROUTING]` |

## Key Metrics

| Metric | Target | Status |
|--------|--------|--------|
| Zero Hallucination Escape Rate | 0% | Verified by 38 integration tests |
| Safe Automation Rate | ≥ 40% | ~55% of questions auto-approve |
| Routing Precision | 100% | All flagged items correctly routed |

## Project Layout

```
.
├── app.py                  # Streamlit UI (3-step flow + KB viewer)
├── api.py                  # FastAPI REST endpoint
├── graph.py                # LangGraph orchestrator
├── models.py               # Pydantic schemas + GraphState
├── config.py               # Env + thresholds
├── agents/
│   ├── intake.py           # Parser & classifier (5 categories)
│   ├── researcher.py       # RAG answerer (offline + optional LLM)
│   └── verifier.py         # Compliance guardrails (7 patterns)
├── retrieval/
│   └── vector_store.py     # TF-IDF + cosine similarity
├── actions/
│   ├── exporter.py         # openpyxl xlsx export
│   ├── email_drafter.py    # Prospect email
│   └── slack_notifier.py   # Slack-style markdown block
├── kb/                     # Acme SaaS policy documents (8 docs)
├── samples/
│   ├── demo_data.py        # Pre-computed demo state
│   ├── build_sample_xlsx.py # Sample .xlsx generator
│   └── *.txt               # Example questionnaires
├── tests/
│   └── test_evaluation.py  # 38 integration tests
└── requirements.txt
```

## Operating Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| Deterministic offline | No API key set | TF-IDF retrieval + template composition. Fully reproducible. |
| LLM-augmented | `OPENAI_API_KEY` or `GROQ_API_KEY` set | Same retrieval; LLM composes final wording from retrieved chunks. |

Both modes share the same retrieval layer and compliance verifier, so the zero-hallucination guarantee holds in either configuration.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check + system info |
| `/api/v1/parse` | POST | Parse questionnaire text into structured questions |
| `/api/v1/run` | POST | Run the full pipeline on raw questionnaire text |
| `/api/v1/stats` | GET | System statistics and guardrail info |

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

## License

MIT
