# 🛡️ TrustLoop

AI-assisted security questionnaire automation for B2B SaaS vendors.
Multi-agent workflow that parses inbound questionnaires, retrieves grounded
evidence from an approved knowledge base, runs compliance guardrails, and
routes risky or low-confidence answers to a human reviewer before any
sales-facing artifact is generated.

This repository implements the **TrustLoop MVP demo** for a single demo
company, **Acme SaaS**, using a static internal policy suite.

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

Orchestrated as a [LangGraph](https://github.com/langchain-ai/langgraph) state
machine. Pydantic schemas enforce the typed `GraphState` channel between nodes.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# (optional) enable LLM-augmented answer composition
cp .env.example .env
# edit .env and set OPENAI_API_KEY

streamlit run app.py
```

Open the URL Streamlit prints (default `http://localhost:8501`).

### Run the demo

1. **Upload tab**: drop `samples/sample_questionnaire.txt` (or paste questions).
2. Click **Parse questions** → confirm the categorized table.
3. Click **Run multi-agent pipeline** → watch the queue populate.
4. **Review tab**: approve / edit / reject every flagged item.
5. **Artifact Hub**: download the filled `.xlsx`, copy the prospect email,
   inspect the Slack notification block.

### Generate the sample `.xlsx`

```bash
python samples/build_sample_xlsx.py
```

### Run the evaluation suite

```bash
pytest tests/ -v
```

All six PRD test cases (TC-001 through TC-006) are covered, plus end-to-end
graph state checks.

## Operating modes

| Mode                    | Trigger                    | Behavior |
|-------------------------|----------------------------|----------|
| Deterministic offline   | No `OPENAI_API_KEY` set    | TF-IDF retrieval + template composition. Fully reproducible, no external calls. |
| LLM-augmented           | `OPENAI_API_KEY` set       | Same retrieval; OpenAI composes the final wording strictly from retrieved chunks. Falls back to offline mode on any error. |

Both modes share the same retrieval layer and the same compliance verifier, so
the zero-hallucination guarantee holds in either configuration.

## Project layout

```
.
├── app.py                  # Streamlit UI (3-step flow)
├── graph.py                # LangGraph orchestrator
├── models.py               # Pydantic schemas + GraphState
├── config.py               # Env + thresholds
├── agents/
│   ├── intake.py           # Parser & classifier
│   ├── researcher.py       # RAG answerer (offline + optional LLM)
│   └── verifier.py         # Compliance guardrails
├── retrieval/
│   └── vector_store.py     # TF-IDF + cosine similarity
├── actions/
│   ├── exporter.py         # openpyxl xlsx export
│   ├── email_drafter.py    # Prospect email
│   └── slack_notifier.py   # Slack-style markdown block
├── kb/                     # Acme SaaS policy documents
├── samples/                # Example questionnaires
├── tests/test_evaluation.py
└── requirements.txt
```

## Safety matrix (Compliance Verifier)

| Trigger                              | Action          | Flag                    |
|--------------------------------------|-----------------|-------------------------|
| Confidence < 0.70                    | Route to human  | `[LOW_CONFIDENCE]`      |
| Mentions HIPAA / PCI-DSS / FedRAMP   | Route to human  | `[CERT_WARNING]`        |
| Absolute legal language              | Route to human  | `[LEGAL_RISK]`          |
| Geographic / residency question      | Route to human  | `[DATA_RESIDENCY]`      |
| Empty evidence after retrieval       | Route to human  | `[MISSING_EVIDENCE]`    |
| Category = `legal`                   | Route to human  | `[ROUTING]`             |
