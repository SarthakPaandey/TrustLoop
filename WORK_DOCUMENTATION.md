# Individual Contribution Document

**Name:** Sarthak Pandey
**Project:** TrustLoop — AI-Assisted Security Questionnaire Automation
**Role:** Individual Contributor

---

## Overview

I worked on TrustLoop, a multi-agent AI system that automates security questionnaire responses for B2B SaaS vendors. My contributions span the product ideation, workflow design with confidence thresholds, product requirements, the full UI/UX landing page and demo page, and the final delivery agent (human review loop, email, Slack, and export).

---

## 1. UI/UX Landing Page & Demo Page

**File:** `app.py` (1,473 lines)

I designed and built the complete user interface from scratch using Streamlit with custom inline CSS and HTML. There are no external UI libraries or frameworks — every visual element was hand-crafted.

### Landing Page
- I created a **space-themed hero section** with an animated starfield background (180 procedurally generated stars with randomized twinkle animations)
- I implemented **nebula blobs** with smooth drift animations for atmospheric depth
- I designed the **navigation bar** with brand identity, anchor links (How it works, Features, Preview), and a gradient CTA button
- I built the **hero section** featuring a gradient headline ("automated, grounded, verified"), professional subtitle, dual CTA buttons, and a 4-stat performance metrics row (0% Hallucination Rate, ~55% Auto-Approved, 100% Routing Precision, <2m Pipeline)
- I created the **"How It Works" section** — a 4-step pipeline visualization showing the multi-agent flow
- I designed the **Features grid** — 6 feature cards with icons explaining the system's capabilities
- I built an **interactive dashboard mockup** that simulates the review panel with real-looking data

### Application Interface (4 Tabs)
- **Upload Tab**: File upload (.xlsx/.txt), paste-to-parse, animated 5-stage pipeline visualization strip, category distribution bar chart, question search/filter
- **Review Tab**: Split-panel review interface with progress tracking, question navigation, color-coded confidence gauge, risk flag badges, evidence citations, inline answer editor, and approve/edit/reject action buttons including bulk "Approve All" — this is the core human-in-the-loop interface
- **Deliver Tab**: Stats dashboard with 4 metric cards, category breakdown chips, XLSX download, prospect email preview, Slack notification mockup
- **KB Tab**: Knowledge base document browser with card grid and tags

### CSS Design System
- I wrote **620+ lines of custom CSS** establishing a complete dark theme design system
- I defined **CSS custom properties** for colors, spacing, and glass effects
- I implemented **glassmorphism** effects on cards and panels
- I added **custom animations** — star twinkling, nebula drifting, planet floating, shooting stars, pipeline stage transitions
- I overrode Streamlit's default styles for a seamless custom experience

### Demo Page
- I built the full interactive demo experience with pre-computed answers
- I implemented the animated pipeline visualization that auto-advances through stages (Upload → Parse → Research → Verify → Deliver)
- I created demo loading mechanisms for instant 30-second demos and 2-minute walkthrough demos

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

## 3. Idea & Workflow Design (with Confidence Thresholds)

I contributed to the overall product idea and workflow design for the multi-agent pipeline, with specific focus on the final delivery stage and confidence threshold system.

### Core Concept
I worked on the idea that **security questionnaires require grounded, verifiable answers — not creative generation**. This principle drove the architecture:
- **Retrieval-first**: Every answer must cite source documents from an approved knowledge base
- **Confidence threshold system**: Answers below a set confidence threshold route to human review rather than auto-approving
- **Human-in-the-loop by design**: Risky items always route to humans, never auto-send

### Confidence Threshold Design
I designed the confidence threshold system (`config.py`):
- `CONFIDENCE_THRESHOLD = 0.70` — answers below this threshold are routed to human review
- `AUTO_SEND_CONFIDENCE_THRESHOLD = 0.70` — average confidence must meet this threshold to auto-email the prospect
- This dual-threshold system ensures both individual answer quality and overall deliverable reliability

### Multi-Agent Pipeline
The system follows a 4-agent pipeline. My focus was on the **Final Actions / Delivery** stage:

```
Raw Input → Intake & Parser → Researcher & Answerer → Compliance Verifier → [Human Review] → Final Actions (Email, Slack, Export)
```

### Human-in-the-Loop Workflow
I designed the review workflow:
- Items flagged by compliance guardrails route to a review queue
- Human reviewers see confidence scores, risk flags, and evidence citations
- Reviewers can Approve, Edit & Approve, or Reject each item
- Bulk "Approve All" for efficient batch processing
- Only after all items are resolved can delivery actions proceed

---

## 4. Delivery Agent — Human Review, Email, Slack & Export

I designed and implemented the complete delivery agent — the final stage of the pipeline that handles human review, prospect communication, and artifact generation.

**Files:** `actions/exporter.py` (109 lines), `actions/email_drafter.py` (59 lines), `actions/auto_email.py` (142 lines), `actions/slack_notifier.py` (36 lines)

### Human Review System (in `app.py`)
- I built the complete review interface with question-by-question navigation
- I implemented the review queue system where flagged items are collected for human review
- I designed the progress tracking showing items reviewed vs items remaining
- I created the approve/edit/reject workflow with status tracking
- I built the auto-approval mechanism for high-confidence answers that pass all guardrails

### Workbook Export (`actions/exporter.py`)
- I implemented XLSX export using openpyxl with professional formatting
- I created a structured workbook with columns: Question ID, Original Question, Status, Answer, Cited Sources, Confidence, Risk Flags
- I added color-coded status fills (green for auto-approved, blue for human-approved, red for rejected, yellow for needs review)
- I built the `summarize_run` function that computes aggregate statistics across all answers

### Prospect Email (`actions/email_drafter.py`)
- I wrote the professional email template for prospect communication
- The email includes: run summary with question counts, auto-approval percentage, human-reviewed items, policy documents referenced
- It communicates next steps (DPA, SOC 2 report availability)

### Auto-Email Sender (`actions/auto_email.py`)
- I built the automated email sending system with SMTP integration
- I implemented pre-flight checks: must have no items still in review, no rejected items, average confidence above threshold
- I designed the dry-run mode for safe preview before sending
- I configured environment-based SMTP settings for flexibility

### Slack Notification (`actions/slack_notifier.py`)
- I built the Slack notification block generator with deal account info, question counts, auto-approval percentage, human-reviewed percentage, and sources referenced
- I added dynamic status emoji (✅ ready for delivery, ⚠️ needs attention)

### Delivery Tab UI
- I designed the stats dashboard showing total questions, auto-approved, human-approved, and rejected counts
- I integrated all three delivery actions (download XLSX, email preview, Slack notification) in a clean 3-column layout
- I implemented the email preview card with subject line and body
- I built the Slack notification mockup with avatar, timestamp, and formatted message

---

## Summary of Deliverables

| Artifact | Lines | Description |
|----------|-------|-------------|
| `app.py` | 1,473 | Streamlit UI — landing page, demo page, review interface, deliver tab |
| `actions/exporter.py` | 109 | XLSX workbook export with formatted Q&A and status colors |
| `actions/email_drafter.py` | 59 | Prospect email template with run summary |
| `actions/auto_email.py` | 142 | Auto-email sender with SMTP integration and confidence threshold checks |
| `actions/slack_notifier.py` | 36 | Slack notification builder for deal pipeline |
| `config.py` | 50 | Confidence thresholds and runtime configuration |
| `README.md` | 189 | PRD & product documentation |

---

*Prepared for individual contribution portfolio review.*
