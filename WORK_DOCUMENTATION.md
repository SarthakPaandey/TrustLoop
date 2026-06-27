# Individual Contribution Document

**Name:** Sarthak Pandey
**Project:** TrustLoop — AI-Assisted Security Questionnaire Automation
**Role:** Individual Contributor

---

## Overview

I worked on TrustLoop, a multi-agent AI system that automates security questionnaire responses for B2B SaaS vendors. My contributions span the product ideation, workflow design, product requirements, UI/UX implementation, and the core researcher agent.

---

## 1. UI/UX Landing Page

**File:** `app.py` (1,473 lines)

I designed and built the complete user interface from scratch using Streamlit with custom inline CSS and HTML. There are no external UI libraries or frameworks — every visual element was hand-crafted.

### Landing Page (What the user sees first)
- I created a **space-themed hero section** with an animated starfield background (180 procedurally generated stars with randomized twinkle animations)
- I implemented **nebula blobs** with smooth drift animations for atmospheric depth
- I designed the **navigation bar** with brand identity, anchor links (How it works, Features, Preview), and a gradient CTA button
- I built the **hero section** featuring a gradient headline ("automated, grounded, verified"), professional subtitle, dual CTA buttons, and a 4-stat performance metrics row (0% Hallucination Rate, ~55% Auto-Approved, 100% Routing Precision, <2m Pipeline)
- I created the **"How It Works" section** — a 4-step pipeline visualization showing the multi-agent flow
- I designed the **Features grid** — 6 feature cards with icons explaining the system's capabilities
- I built an **interactive dashboard mockup** that simulates the review panel with real-looking data

### Application Interface (4 tabs)
- **Upload Tab**: I implemented file upload (.xlsx/.txt), paste-to-parse functionality, an animated 5-stage pipeline visualization strip (Upload → Parse → Research → Verify → Deliver), category distribution bar chart, and question search/filter
- **Review Tab**: I built a split-panel review interface with progress tracking, question navigation (prev/next/dropdown), a color-coded confidence gauge that changes based on threshold (green/amber/red), risk flag badges with semantic icons, evidence citations, inline answer editor, and approve/edit/reject action buttons including a bulk "Approve All" feature
- **Deliver Tab**: I created a stats dashboard showing 4 metric cards, category breakdown chips, XLSX workbook download, prospect email preview with subject line, and Slack notification mockup
- **KB Tab**: I built a knowledge base document browser with a card grid layout, auto-generated tags, and section previews

### CSS Design System
- I wrote **620+ lines of custom CSS** establishing a complete dark theme design system
- I defined **CSS custom properties** for colors, spacing, and glass effects
- I implemented **glassmorphism** effects on cards and panels
- I added **custom animations** — star twinkling, nebula drifting, planet floating, shooting stars, pipeline stage transitions
- I overrode Streamlit's default styles for a seamless custom experience

---

## 2. Product Requirements Document (PRD)

I defined the complete product requirements for TrustLoop, documented in `README.md`.

### Problem Definition
I identified three core pain points in the B2B SaaS sales cycle:
- Sales engineers lack the technical security knowledge to answer questionnaires
- Security/compliance teams are bottlenecked by repetitive manual reviews
- Off-the-shelf LLMs hallucinate certifications, SLAs, and security claims

### Solution Design
I architected a system combining:
- RAG (Retrieval-Augmented Generation) for grounded answers
- LangGraph state machine for deterministic agentic workflow
- Compliance guardrails for safety validation
- Human-in-the-loop for risk management

### Safety Matrix
I defined 7 trigger-action-flag patterns that govern the system's safety behavior:

| Trigger | Action | Flag |
|---------|--------|------|
| Confidence < 0.70 | Route to human | `[LOW_CONFIDENCE]` |
| Mentions HIPAA / PCI-DSS / FedRAMP | Route to human | `[CERT_WARNING]` |
| Absolute legal language | Route to human | `[LEGAL_RISK]` |
| Geographic / residency question | Route to human | `[DATA_RESIDENCY]` |
| Empty evidence after retrieval | Route to human | `[MISSING_EVIDENCE]` |
| Category = `legal` | Route to human | `[ROUTING]` |
| Insurance-related question | Route to human | `[ROUTING]` |

### Key Metrics
I set and tracked performance targets:
- 0% Hallucination Escape Rate
- ≥ 40% Safe Automation Rate (achieved ~55%)
- 100% Routing Precision

### API Specification
I specified 4 REST API endpoints with request/response schemas:
- `GET /api/v1/health` — Health check
- `POST /api/v1/parse` — Parse questionnaire text
- `POST /api/v1/run` — Run full pipeline
- `GET /api/v1/stats` — System statistics

### Operating Modes
I defined two operating modes:
- **Deterministic offline** — fully reproducible without any API keys
- **LLM-augmented** — optional LLM composition via OpenAI or Groq

### Demo Script
I wrote a complete YC presentation demo script with three options:
- 30-second instant demo
- 2-minute live pipeline walkthrough
- 1-minute API demo with curl commands

---

## 3. Idea & Workflow Design

I designed the entire multi-agent workflow and system architecture.

### Core Concept
I originated the idea that **security questionnaires require grounded, verifiable answers — not creative generation**. This principle drove every architectural decision:
- **Retrieval-first**: Every answer must cite source documents from an approved knowledge base
- **Deterministic by default**: The system works without any LLM API keys
- **Human-in-the-loop by design**: Risky items always route to humans, never auto-send

### Multi-Agent Pipeline
I designed a 4-agent pipeline with single responsibilities:

| Agent | Responsibility |
|-------|---------------|
| Intake & Parser | Split questions, classify into 5 categories |
| Researcher & Answerer | RAG retrieval + answer composition |
| Compliance Verifier | Run 7 safety heuristics |
| Final Actions | Export, email, Slack notification |

### State Machine Design
I designed the LangGraph state machine (`graph.py`) with typed state channels:

```
intake → research_and_verify → [auto-approved | human review] → final_actions
```

- Human review is intentionally external — the UI advances the queue interactively
- Typed `GraphState` (TypedDict) ensures data integrity across nodes
- State channels: `raw_input`, `questions`, `answers`, `review_queue`, `final_status`, `actions_taken`

### Data Models
I defined the complete data model (`models.py`):
- `Question` — with UUID, text, and 5-category classification
- `Answer` — with draft, evidence citations, confidence score, risk flags, and lifecycle status
- `GraphState` — LangGraph typed state with all pipeline channels

### Category Classification System
I designed a heuristic classifier (`intake.py`) that categorizes questions into 5 priority-ordered types:
1. `certification` — SOC 2, HIPAA, PCI, FedRAMP (highest priority)
2. `legal` — guarantees, warranties, liabilities
3. `data-privacy` — data storage, residency, subprocessors
4. `technical` — encryption, MFA, firewalls, backups
5. `general` — fallback category

### Compliance Guardrails
I authored the verifier agent (`agents/verifier.py`, 142 lines) implementing 7 deterministic safety heuristics:
- Certification pattern matching for 6 certification types
- Legal absolute language detection (regex)
- Geographic/residency question triggers
- Evidence presence validation
- Confidence threshold checks
- Legal category routing
- Insurance-related question detection

---

## 4. Researcher Agent

I designed and implemented the core RAG agent (`agents/researcher.py`, 174 lines) and the TF-IDF vector store (`retrieval/vector_store.py`, 111 lines).

### Vector Store Design
I built a TF-IDF backed retriever using scikit-learn:
- **TF-IDF + cosine similarity** — chosen for reproducibility (no API keys needed)
- **Bigram n-grams** for improved phrase matching
- **Markdown-aware chunking** — splits KB documents by `##` headings, preserving section context
- **Singleton pattern** — process-wide instance for efficiency
- **Minimum score threshold** (0.08) — filters irrelevant chunks so the agent can truthfully say "no grounded evidence"

### Confidence Scoring Algorithm
I designed a multi-factor confidence scoring system:

| Factor | What it measures | Impact |
|--------|-----------------|--------|
| Base score | TF-IDF cosine score mapped to 6 confidence tiers | 0.10–0.85 |
| Gap bonus | Score gap between top and runner-up match | +0.00–0.12 |
| Multi-chunk bonus | Number of supporting chunks found | +0.00–0.08 |
| Cert penalty | Caps confidence for unsupported certifications | Cap at 0.50 |

The scoring tiers are:
- Score ≥ 0.25 → base 0.85
- Score ≥ 0.18 → base 0.80
- Score ≥ 0.12 → base 0.75
- Score ≥ 0.10 → base 0.72
- Score ≥ 0.08 → base 0.65
- Score ≥ 0.05 → base 0.45
- Score < 0.05 → max(0.10, score × 3.0)

### Answer Composition — Dual Mode
I implemented two composition strategies:

**1. Offline mode (deterministic)** — `_compose_offline()`:
- Extracts top lines from each chunk (max 320 chars)
- Formats as bullet points with source citations
- Example: `"- [snippet] (source: encryption_policy.md#aes-256_encryption)"`

**2. LLM mode (optional)** — `_compose_llm()`:
- System prompt enforces strict grounding rules
- Temperature 0.0 for deterministic output
- Falls back to offline mode gracefully on errors
- Handles `NO_EVIDENCE` responses from LLM
- Supports both OpenAI (GPT-4o-mini) and Groq (Llama 3.3) providers

### Knowledge Base Curation
I created 10 markdown policy documents covering the full security domain:
Access Control, Business Continuity, Compliance Certifications, Data Storage, Employee Security, Encryption, General Security, Incident Response, Network Security, and SLA & Insurance.

---

## 5. Test Suite & Verification

I wrote **38 integration tests** (`tests/test_evaluation.py`, 319 lines) covering:
- TC-001 to TC-006: Original PRD test scenarios
- 12 parametrized routing precision tests
- 6 verifier edge cases
- 3 researcher grounding tests
- 4 demo data integrity tests
- 4 export and action generation tests
- 3 end-to-end pipeline tests

---

## Summary of Deliverables

| Artifact | Lines | Description |
|----------|-------|-------------|
| `app.py` | 1,473 | Complete Streamlit UI with space-themed landing page |
| `agents/researcher.py` | 174 | RAG answerer with multi-factor confidence scoring |
| `retrieval/vector_store.py` | 111 | TF-IDF vector store |
| `agents/verifier.py` | 142 | 7-guardrail compliance verifier |
| `agents/intake.py` | 123 | Parser & classifier |
| `graph.py` | 67 | LangGraph orchestrator |
| `models.py` | 63 | Data models |
| `config.py` | 50 | Runtime configuration |
| `api.py` | 162 | REST API |
| `README.md` | 189 | PRD & documentation |
| `tests/test_evaluation.py` | 319 | 38 integration tests |
| `kb/*.md` (10 files) | ~270 | Knowledge base documents |

---

*Prepared for individual contribution portfolio review.*
