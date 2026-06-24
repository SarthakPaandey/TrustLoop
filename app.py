"""TrustLoop — Streamlit UI.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from actions import (
    build_slack_notification,
    draft_prospect_email,
    export_workbook,
    summarize_run,
)
from agents import parse_questionnaire
from config import COMPANY_NAME, PROSPECT_NAME, USE_LLM
from graph import run_pipeline
from models import Answer

st.set_page_config(
    page_title="TrustLoop",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================================
#                              GLOBAL STYLES
# ============================================================================

CSS = """
<style>
/* ---- base shell ---- */
.block-container { padding-top: 1.2rem; max-width: 1280px; }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

html, body, [class*="css"] {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* ---- hero ---- */
.tl-hero {
  background: linear-gradient(135deg, #0E1B33 0%, #112243 45%, #1A2D5C 100%);
  border: 1px solid #1F2A44;
  border-radius: 16px;
  padding: 22px 26px;
  margin-bottom: 18px;
  display: flex; justify-content: space-between; align-items: center;
  box-shadow: 0 8px 30px rgba(0,0,0,0.25);
}
.tl-hero-left { display:flex; align-items:center; gap:16px; }
.tl-logo {
  width: 56px; height: 56px; border-radius: 14px;
  background: linear-gradient(135deg, #22D3EE, #0EA5E9);
  display:flex; align-items:center; justify-content:center;
  font-size: 28px; box-shadow: 0 6px 20px rgba(34,211,238,0.35);
}
.tl-brand { line-height: 1.15; }
.tl-brand h1 { margin:0; font-size: 28px; letter-spacing:-0.02em; }
.tl-brand .sub { color: #94A3B8; font-size: 13px; margin-top: 4px; }

.tl-meta { display:flex; gap:8px; flex-wrap: wrap; justify-content:flex-end; }
.tl-pill {
  background: #0F1B33; border:1px solid #233252; color:#CBD5E1;
  padding: 6px 12px; border-radius: 999px; font-size: 12px; font-weight: 500;
}
.tl-pill.live { background: rgba(16,185,129,0.10); border-color: #10B981; color:#6EE7B7; }
.tl-pill.mode { background: rgba(34,211,238,0.10); border-color: #22D3EE; color:#67E8F9; }

/* ---- step rail ---- */
.tl-rail { display:flex; gap:10px; margin: 4px 0 22px 0; }
.tl-step {
  flex:1; background:#121A2B; border:1px solid #1F2A44;
  border-radius: 12px; padding: 12px 14px; position: relative;
}
.tl-step.active { border-color: #22D3EE; box-shadow: 0 0 0 2px rgba(34,211,238,0.15); }
.tl-step.done { border-color: #10B981; }
.tl-step .num {
  width:26px; height:26px; border-radius: 50%;
  background:#1F2A44; color:#94A3B8;
  display:inline-flex; align-items:center; justify-content:center;
  font-weight:600; font-size:12px; margin-right:8px;
}
.tl-step.active .num { background:#22D3EE; color:#0B1220; }
.tl-step.done .num { background:#10B981; color:#0B1220; }
.tl-step .label { font-weight: 600; font-size: 13px; color:#E5E7EB; }
.tl-step .desc { color:#94A3B8; font-size: 11.5px; margin-top: 2px; }

/* ---- metric tiles ---- */
.tl-metrics { display:grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 4px 0 18px; }
.tl-metric {
  background: linear-gradient(180deg, #121A2B 0%, #0F172A 100%);
  border: 1px solid #1F2A44; border-radius: 14px; padding: 16px;
}
.tl-metric .k { color:#94A3B8; font-size:11px; text-transform: uppercase; letter-spacing: 0.08em; font-weight:600; }
.tl-metric .v { color:#F1F5F9; font-size: 30px; font-weight: 700; letter-spacing:-0.02em; margin-top: 6px; }
.tl-metric .sub { font-size: 11.5px; color:#64748B; margin-top: 2px; }
.tl-metric.ok .v { color:#34D399; }
.tl-metric.warn .v { color:#FBBF24; }
.tl-metric.danger .v { color:#F87171; }
.tl-metric.accent .v { color:#67E8F9; }

/* ---- category badges ---- */
.tl-cat {
  display:inline-block; padding:3px 10px; border-radius:999px;
  font-size: 11px; font-weight:600; letter-spacing:0.02em;
}
.tl-cat.technical     { background:rgba(34,211,238,0.12);  color:#67E8F9; border:1px solid rgba(34,211,238,0.35); }
.tl-cat.certification { background:rgba(168,85,247,0.12);  color:#C4B5FD; border:1px solid rgba(168,85,247,0.35); }
.tl-cat.legal         { background:rgba(239,68,68,0.12);   color:#FCA5A5; border:1px solid rgba(239,68,68,0.35); }
.tl-cat.data-privacy  { background:rgba(245,158,11,0.12);  color:#FCD34D; border:1px solid rgba(245,158,11,0.35); }
.tl-cat.general       { background:rgba(148,163,184,0.12); color:#CBD5E1; border:1px solid rgba(148,163,184,0.35); }

/* ---- status pills ---- */
.tl-status { padding:3px 10px; border-radius:999px; font-size:11px; font-weight:600; letter-spacing:0.02em; }
.tl-status.auto_approved  { background:rgba(16,185,129,0.14); color:#34D399; border:1px solid rgba(16,185,129,0.35); }
.tl-status.human_approved { background:rgba(56,189,248,0.14); color:#7DD3FC; border:1px solid rgba(56,189,248,0.35); }
.tl-status.needs_review   { background:rgba(245,158,11,0.14); color:#FCD34D; border:1px solid rgba(245,158,11,0.40); }
.tl-status.rejected       { background:rgba(239,68,68,0.14);  color:#F87171; border:1px solid rgba(239,68,68,0.40); }

/* ---- review card ---- */
.tl-card {
  background: linear-gradient(180deg, #121A2B 0%, #0E1525 100%);
  border:1px solid #1F2A44; border-radius:16px; padding:20px;
  box-shadow: 0 6px 24px rgba(0,0,0,0.25);
}
.tl-card-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; }
.tl-card-id { color:#94A3B8; font-size:11px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing:0.04em; }
.tl-card-title { color:#F1F5F9; font-size:18px; font-weight:600; line-height:1.35; margin: 4px 0 14px; }

.tl-section-label { color:#64748B; font-size:11px; text-transform:uppercase; letter-spacing:0.10em; font-weight:600; margin: 6px 0 6px; }

/* ---- confidence gauge ---- */
.tl-gauge-wrap {
  background: #0B1220; border:1px solid #1F2A44; border-radius: 12px;
  padding: 14px 16px;
}
.tl-gauge-bar {
  position: relative; height: 10px; background: #1F2A44; border-radius: 999px; overflow: hidden;
}
.tl-gauge-fill { position:absolute; top:0; left:0; bottom:0; border-radius:999px; }
.tl-gauge-row { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px; }
.tl-gauge-num { font-size:24px; font-weight:700; letter-spacing:-0.02em; }
.tl-gauge-thr { color:#64748B; font-size:11px; }

/* ---- flag chips ---- */
.tl-flag {
  display:flex; align-items:flex-start; gap:8px;
  background: rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.30);
  color:#FCD34D; border-radius:10px; padding:9px 12px; font-size:12.5px;
  margin-bottom: 8px; line-height:1.45;
}
.tl-flag.cert     { background: rgba(168,85,247,0.10); border-color: rgba(168,85,247,0.35); color:#DDD6FE; }
.tl-flag.legal    { background: rgba(239,68,68,0.10);  border-color: rgba(239,68,68,0.35);  color:#FCA5A5; }
.tl-flag.geo      { background: rgba(245,158,11,0.10); border-color: rgba(245,158,11,0.35); color:#FCD34D; }
.tl-flag.missing  { background: rgba(148,163,184,0.10);border-color: rgba(148,163,184,0.35); color:#CBD5E1; }
.tl-flag.lowconf  { background: rgba(56,189,248,0.10); border-color: rgba(56,189,248,0.35); color:#7DD3FC; }
.tl-flag .ico { font-size: 14px; line-height:1; margin-top:1px; }

/* ---- citations ---- */
.tl-cite {
  display:inline-block; background:#0B1220; border:1px solid #1F2A44;
  color:#7DD3FC; padding:5px 10px; border-radius:8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11.5px;
  margin: 0 6px 6px 0;
}

/* ---- artifact cards ---- */
.tl-artifact {
  background: linear-gradient(180deg, #121A2B 0%, #0E1525 100%);
  border:1px solid #1F2A44; border-radius:16px; padding:18px; height:100%;
  box-shadow: 0 6px 24px rgba(0,0,0,0.20);
}
.tl-artifact-head { display:flex; align-items:center; gap:10px; margin-bottom: 12px; }
.tl-artifact-icon { width:38px; height:38px; border-radius:10px;
  display:flex; align-items:center; justify-content:center; font-size:18px;
  background: rgba(34,211,238,0.10); border:1px solid rgba(34,211,238,0.30);
}
.tl-artifact-title { color:#F1F5F9; font-weight:600; font-size: 15px; }
.tl-artifact-sub { color:#64748B; font-size:11.5px; }

/* ---- slack mockup ---- */
.tl-slack {
  background:#1A1D21; border-radius:10px; padding:14px 16px;
  font-family: 'Lato', -apple-system, sans-serif; color:#D1D2D3;
}
.tl-slack-row { display:flex; gap:10px; }
.tl-slack-avatar {
  width: 36px; height: 36px; border-radius:6px;
  background: linear-gradient(135deg,#22D3EE,#0EA5E9);
  display:flex; align-items:center; justify-content:center; font-size:18px; flex-shrink:0;
}
.tl-slack-name { color:#FFFFFF; font-weight: 700; font-size: 14px; }
.tl-slack-time { color:#8E9297; font-size: 11px; margin-left: 6px; }
.tl-slack-body { font-size: 13.5px; line-height: 1.55; white-space: pre-wrap; margin-top: 2px; }

/* ---- email mockup ---- */
.tl-email {
  background:#0B1220; border:1px solid #1F2A44; border-radius:10px; overflow:hidden;
}
.tl-email-head { background:#121A2B; padding: 10px 14px; border-bottom:1px solid #1F2A44; font-size:12px; color:#94A3B8; }
.tl-email-head b { color:#E5E7EB; }
.tl-email-body { padding: 14px; font-size: 13px; color:#CBD5E1; white-space: pre-wrap; line-height:1.55;
  max-height: 280px; overflow-y: auto;
}

/* ---- buttons polish ---- */
.stButton > button {
  border-radius: 10px; font-weight: 600;
  transition: transform 0.08s ease, box-shadow 0.12s ease;
}
.stButton > button:hover { transform: translateY(-1px); }

/* ---- file uploader ---- */
[data-testid="stFileUploaderDropzone"] {
  background: #0F1B33; border:2px dashed #2A3A60; border-radius:12px;
}

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid #1F2A44; }
.stTabs [data-baseweb="tab"] {
  background: transparent; color:#94A3B8; border-radius: 8px 8px 0 0; padding: 10px 16px;
}
.stTabs [aria-selected="true"] { color:#67E8F9 !important; background: rgba(34,211,238,0.06); }
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


# ============================================================================
#                              SESSION STATE
# ============================================================================

def _init_state() -> None:
    defaults: dict[str, object] = {
        "questions": [],
        "answers": [],
        "review_queue": [],
        "final_status": "idle",
        "run_complete": False,
        "selected_review_id": None,
        "current_step": 1,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def _answer_by_id(qid: str) -> Answer | None:
    for a in st.session_state.answers:
        if a.question_id == qid:
            return a
    return None


def _update_answer(updated: Answer) -> None:
    answers: list[Answer] = st.session_state.answers
    for i, a in enumerate(answers):
        if a.question_id == updated.question_id:
            answers[i] = updated
            break
    st.session_state.review_queue = [
        a.question_id for a in answers if a.status == "needs_review"
    ]
    if not st.session_state.review_queue:
        st.session_state.final_status = "completed"
        st.session_state.current_step = 3


# ============================================================================
#                              HELPERS
# ============================================================================

def _cat_badge(category: str) -> str:
    return f'<span class="tl-cat {category}">{category.replace("-", " ")}</span>'


def _status_pill(status: str) -> str:
    label = status.replace("_", " ").title()
    return f'<span class="tl-status {status}">{label}</span>'


def _flag_class(flag: str) -> str:
    if "[CERT_WARNING]" in flag: return "cert"
    if "[LEGAL_RISK]" in flag: return "legal"
    if "[DATA_RESIDENCY]" in flag: return "geo"
    if "[MISSING_EVIDENCE]" in flag: return "missing"
    if "[LOW_CONFIDENCE]" in flag: return "lowconf"
    return ""


def _flag_icon(flag: str) -> str:
    if "[CERT_WARNING]" in flag: return "🎓"
    if "[LEGAL_RISK]" in flag: return "⚖️"
    if "[DATA_RESIDENCY]" in flag: return "🌍"
    if "[MISSING_EVIDENCE]" in flag: return "🔍"
    if "[LOW_CONFIDENCE]" in flag: return "📉"
    if "[ROUTING]" in flag: return "🧭"
    return "⚠️"


# ============================================================================
#                              HERO + STEP RAIL
# ============================================================================

_init_state()

mode_label = "LLM-augmented" if USE_LLM else "Deterministic offline"

st.markdown(
    f"""
    <div class="tl-hero">
      <div class="tl-hero-left">
        <div class="tl-logo">🛡️</div>
        <div class="tl-brand">
          <h1>TrustLoop</h1>
          <div class="sub">AI-assisted security questionnaire automation
          · Vendor <b>{COMPANY_NAME}</b> · Deal <b>{PROSPECT_NAME}</b></div>
        </div>
      </div>
      <div class="tl-meta">
        <span class="tl-pill live">● Live</span>
        <span class="tl-pill mode">{mode_label}</span>
        <span class="tl-pill">Threshold C ≥ 0.70</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Step rail
step = st.session_state.current_step
def _stepcls(n: int) -> str:
    if step == n: return "tl-step active"
    if step > n: return "tl-step done"
    return "tl-step"

st.markdown(
    f"""
    <div class="tl-rail">
      <div class="{_stepcls(1)}"><span class="num">1</span>
        <span class="label">Upload & Parse</span>
        <div class="desc">Ingest the questionnaire and classify questions.</div>
      </div>
      <div class="{_stepcls(2)}"><span class="num">2</span>
        <span class="label">Agentic Review</span>
        <div class="desc">RAG + compliance guardrails; route to human if risky.</div>
      </div>
      <div class="{_stepcls(3)}"><span class="num">3</span>
        <span class="label">Deliverables</span>
        <div class="desc">Workbook, prospect email, Slack notification.</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_upload, tab_review, tab_artifacts = st.tabs(
    ["📥  Upload & Parse", "🧪  Queue & Review", "📦  Artifact Hub"]
)


# ============================================================================
#                              STEP 1 — UPLOAD
# ============================================================================

with tab_upload:
    col_l, col_r = st.columns([1.1, 1])

    with col_l:
        st.markdown('<div class="tl-section-label">Upload questionnaire</div>', unsafe_allow_html=True)
        uploaded = st.file_uploader(
            "Drop an .xlsx or .txt — one question per line",
            type=["xlsx", "txt"],
            accept_multiple_files=False,
            label_visibility="collapsed",
        )
        st.markdown('<div class="tl-section-label" style="margin-top:14px;">…or paste questions</div>', unsafe_allow_html=True)
        pasted = st.text_area(
            "Paste",
            height=160,
            label_visibility="collapsed",
            placeholder=(
                "Do you encrypt data at rest?\n"
                "Are you HIPAA certified?\n"
                "Where is customer data stored?"
            ),
        )

        b1, b2 = st.columns([1, 1])
        if b1.button("Parse questions", use_container_width=True):
            raw_text: str | None = None
            if uploaded is not None:
                if uploaded.name.lower().endswith(".xlsx"):
                    tmp = Path("./_uploaded.xlsx")
                    tmp.write_bytes(uploaded.getvalue())
                    st.session_state.questions = parse_questionnaire(tmp)
                    tmp.unlink(missing_ok=True)
                else:
                    raw_text = uploaded.getvalue().decode("utf-8", errors="ignore")
            elif pasted.strip():
                raw_text = pasted

            if raw_text is not None:
                st.session_state.questions = parse_questionnaire(raw_text)

            if st.session_state.questions:
                st.session_state.current_step = 1
                st.toast(f"Parsed {len(st.session_state.questions)} question(s).", icon="✅")
            else:
                st.warning("Nothing to parse yet — upload a file or paste questions.")

        if st.session_state.questions and b2.button(
            "▶ Run multi-agent pipeline", type="primary", use_container_width=True
        ):
            with st.status("Running multi-agent pipeline…", expanded=True) as status:
                st.write("📋 **Intake & Parser** — classifying questions")
                time.sleep(0.35)
                st.write("🔎 **Researcher** — retrieving grounded evidence from KB")
                time.sleep(0.45)
                st.write("🛡 **Compliance Verifier** — running safety heuristics")
                time.sleep(0.35)
                raw = "\n".join(q.text for q in st.session_state.questions)
                state = run_pipeline(raw)
                st.session_state.questions = list(state["questions"])
                st.session_state.answers = list(state["answers"])
                st.session_state.review_queue = list(state["review_queue"])
                st.session_state.final_status = state["final_status"]
                st.session_state.run_complete = state["final_status"] == "completed"
                st.session_state.current_step = 3 if not state["review_queue"] else 2
                st.write(
                    f"✅ Done — **{len(state['answers'])}** answered, "
                    f"**{len(state['review_queue'])}** awaiting review."
                )
                status.update(label="Pipeline complete", state="complete")
            st.toast("Pipeline complete — open the Queue tab.", icon="🚀")

    with col_r:
        st.markdown('<div class="tl-section-label">Parsed questions</div>', unsafe_allow_html=True)
        if not st.session_state.questions:
            st.markdown(
                """
                <div class="tl-card" style="text-align:center; color:#64748B; padding:36px 18px;">
                  <div style="font-size:36px; margin-bottom:8px;">📥</div>
                  <div style="font-size:13.5px;">No questions parsed yet.<br>
                  Upload a file or paste questions, then click <b>Parse questions</b>.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            rows_html = []
            for q in st.session_state.questions:
                rows_html.append(
                    f"""
                    <div style="display:flex; gap:10px; padding:10px 12px;
                                border-bottom:1px solid #1F2A44; align-items:flex-start;">
                      <code style="color:#64748B; font-size:11px; min-width:88px;">{q.id}</code>
                      <div style="flex:1; color:#E5E7EB; font-size:13px; line-height:1.5;">{q.text}</div>
                      <div>{_cat_badge(q.category)}</div>
                    </div>
                    """
                )
            st.markdown(
                f'<div class="tl-card" style="padding:6px;">{"".join(rows_html)}</div>',
                unsafe_allow_html=True,
            )

            # Category breakdown
            cats = pd.Series([q.category for q in st.session_state.questions]).value_counts()
            chips = " ".join(
                f'<span class="tl-cat {c}" style="margin-right:6px;">{c.replace("-"," ")} · {n}</span>'
                for c, n in cats.items()
            )
            st.markdown(
                f'<div style="margin-top:12px;">{chips}</div>',
                unsafe_allow_html=True,
            )


# ============================================================================
#                              STEP 2 — REVIEW
# ============================================================================

with tab_review:
    answers: list[Answer] = st.session_state.answers
    if not answers:
        st.markdown(
            """
            <div class="tl-card" style="text-align:center; color:#64748B; padding:42px 18px;">
              <div style="font-size:36px; margin-bottom:8px;">🧪</div>
              <div style="font-size:13.5px;">No run yet. Head to <b>Upload & Parse</b>
              and click <b>Run multi-agent pipeline</b>.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        s = summarize_run(answers)
        st.markdown(
            f"""
            <div class="tl-metrics">
              <div class="tl-metric"><div class="k">Total</div>
                <div class="v">{s.total}</div><div class="sub">questions</div></div>
              <div class="tl-metric ok"><div class="k">Auto-approved</div>
                <div class="v">{s.auto_approved}</div>
                <div class="sub">{s.auto_pct:.0f}% safe path</div></div>
              <div class="tl-metric warn"><div class="k">Needs review</div>
                <div class="v">{s.needs_review}</div>
                <div class="sub">pending sign-off</div></div>
              <div class="tl-metric accent"><div class="k">Human-approved</div>
                <div class="v">{s.human_approved}</div>
                <div class="sub">cleared by reviewer</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if s.needs_review == 0:
            st.success("🎉 Queue cleared — every item has reached a terminal state. Head to the Artifact Hub.")
            st.balloons()
        else:
            queue_ids = st.session_state.review_queue
            label_for = {
                qid: f"{qid} · {next(a.question_text for a in answers if a.question_id == qid)[:80]}"
                for qid in queue_ids
            }
            st.markdown('<div class="tl-section-label">Review queue</div>', unsafe_allow_html=True)
            selected = st.selectbox(
                "Select an item",
                options=queue_ids,
                format_func=lambda qid: label_for.get(qid, qid),
                key="review_selector",
                label_visibility="collapsed",
            )
            st.session_state.selected_review_id = selected
            current = _answer_by_id(selected)
            if current is not None:
                question_obj = next(
                    (q for q in st.session_state.questions if q.id == current.question_id),
                    None,
                )
                cat = question_obj.category if question_obj else "general"
                cat_badge = _cat_badge(cat)
                status_pill = _status_pill(current.status)

                st.markdown(
                    f"""
                    <div class="tl-card">
                      <div class="tl-card-head">
                        <div class="tl-card-id">{current.question_id}</div>
                        <div>{cat_badge} &nbsp; {status_pill}</div>
                      </div>
                      <div class="tl-card-title">{current.question_text}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.write("")

                left, right = st.columns([0.95, 1.05])

                with left:
                    # Confidence gauge
                    pct = int(current.confidence * 100)
                    if current.confidence >= 0.70:
                        bar_grad = "linear-gradient(90deg,#34D399,#10B981)"
                        label_color = "#34D399"
                    elif current.confidence >= 0.40:
                        bar_grad = "linear-gradient(90deg,#FBBF24,#F59E0B)"
                        label_color = "#FBBF24"
                    else:
                        bar_grad = "linear-gradient(90deg,#F87171,#EF4444)"
                        label_color = "#F87171"
                    st.markdown(
                        f"""
                        <div class="tl-gauge-wrap">
                          <div class="tl-section-label" style="margin-top:0;">Confidence</div>
                          <div class="tl-gauge-row">
                            <div class="tl-gauge-num" style="color:{label_color};">{pct}%</div>
                            <div class="tl-gauge-thr">threshold 70%</div>
                          </div>
                          <div class="tl-gauge-bar">
                            <div class="tl-gauge-fill" style="width:{pct}%; background:{bar_grad};"></div>
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    st.markdown('<div class="tl-section-label" style="margin-top:14px;">Risk flags</div>', unsafe_allow_html=True)
                    if current.risk_flags:
                        flags_html = "".join(
                            f'<div class="tl-flag {_flag_class(f)}">'
                            f'<span class="ico">{_flag_icon(f)}</span><div>{f}</div></div>'
                            for f in current.risk_flags
                        )
                        st.markdown(flags_html, unsafe_allow_html=True)
                    else:
                        st.caption("No active flags.")

                    st.markdown('<div class="tl-section-label" style="margin-top:14px;">Cited sources</div>', unsafe_allow_html=True)
                    if current.evidence:
                        chips = "".join(f'<span class="tl-cite">📄 {c}</span>' for c in current.evidence)
                        st.markdown(chips, unsafe_allow_html=True)
                    else:
                        st.caption("No grounded sources retrieved.")

                with right:
                    st.markdown('<div class="tl-section-label" style="margin-top:0;">Drafted answer (editable)</div>', unsafe_allow_html=True)
                    edited = st.text_area(
                        "Drafted answer",
                        value=current.draft,
                        height=260,
                        label_visibility="collapsed",
                        key=f"draft_{current.question_id}",
                    )

                    bc1, bc2, bc3 = st.columns(3)
                    if bc1.button("✅ Approve", type="primary",
                                  use_container_width=True, key=f"approve_{current.question_id}"):
                        _update_answer(
                            current.model_copy(update={"draft": edited, "status": "human_approved"})
                        )
                        st.toast("Approved.", icon="✅")
                        st.rerun()
                    if bc2.button("✏️ Edit & Approve",
                                  use_container_width=True, key=f"edit_{current.question_id}"):
                        _update_answer(
                            current.model_copy(update={"draft": edited, "status": "human_approved"})
                        )
                        st.toast("Edited and approved.", icon="✏️")
                        st.rerun()
                    if bc3.button("❌ Reject",
                                  use_container_width=True, key=f"reject_{current.question_id}"):
                        _update_answer(
                            current.model_copy(update={"draft": edited, "status": "rejected"})
                        )
                        st.toast("Rejected.", icon="❌")
                        st.rerun()


# ============================================================================
#                              STEP 3 — ARTIFACT HUB
# ============================================================================

with tab_artifacts:
    answers = st.session_state.answers
    if not answers:
        st.markdown(
            """
            <div class="tl-card" style="text-align:center; color:#64748B; padding:42px 18px;">
              <div style="font-size:36px; margin-bottom:8px;">📦</div>
              <div style="font-size:13.5px;">Artifacts appear once the pipeline has run.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif st.session_state.review_queue:
        st.markdown(
            f"""
            <div class="tl-card" style="border-color: rgba(245,158,11,0.45);">
              <div style="display:flex; align-items:center; gap:10px;">
                <div style="font-size:24px;">⏳</div>
                <div>
                  <div style="font-weight:600; color:#FCD34D;">
                    {len(st.session_state.review_queue)} item(s) still need review
                  </div>
                  <div style="color:#94A3B8; font-size:12.5px;">
                    Artifacts unlock once the queue is empty.
                  </div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        s = summarize_run(answers)
        # Mini-summary row at the top
        st.markdown(
            f"""
            <div class="tl-metrics" style="grid-template-columns: repeat(4, 1fr);">
              <div class="tl-metric"><div class="k">Total</div>
                <div class="v">{s.total}</div></div>
              <div class="tl-metric ok"><div class="k">Auto</div>
                <div class="v">{s.auto_approved}</div></div>
              <div class="tl-metric accent"><div class="k">Reviewed</div>
                <div class="v">{s.human_approved}</div></div>
              <div class="tl-metric danger"><div class="k">Rejected</div>
                <div class="v">{s.rejected}</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Full answer table
        st.markdown('<div class="tl-section-label">Final response matrix</div>', unsafe_allow_html=True)
        df = pd.DataFrame([
            {
                "ID": a.question_id,
                "Status": a.status.replace("_", " ").title(),
                "Question": a.question_text,
                "Answer": a.draft,
                "Confidence": f"{a.confidence:.2f}",
                "Sources": ", ".join(a.evidence) if a.evidence else "—",
            }
            for a in answers
        ])
        st.dataframe(df, hide_index=True, use_container_width=True, height=240)

        st.write("")
        a_col, b_col, c_col = st.columns(3)

        # ---- Card A: workbook ----
        with a_col:
            st.markdown(
                """
                <div class="tl-artifact">
                  <div class="tl-artifact-head">
                    <div class="tl-artifact-icon">📊</div>
                    <div>
                      <div class="tl-artifact-title">Filled Questionnaire</div>
                      <div class="tl-artifact-sub">openpyxl · color-coded status</div>
                    </div>
                  </div>
                """,
                unsafe_allow_html=True,
            )
            tmp_path = export_workbook(answers, filename="trustloop_export.xlsx")
            buf = io.BytesIO(tmp_path.read_bytes())
            st.download_button(
                "⬇  Download workbook",
                data=buf,
                file_name="trustloop_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

        # ---- Card B: email ----
        with b_col:
            email_body = draft_prospect_email(answers)
            first_line, _, rest = email_body.partition("\n\n")
            subject_line = first_line.replace("Subject: ", "")
            st.markdown(
                f"""
                <div class="tl-artifact">
                  <div class="tl-artifact-head">
                    <div class="tl-artifact-icon">✉️</div>
                    <div>
                      <div class="tl-artifact-title">Prospect Email Draft</div>
                      <div class="tl-artifact-sub">To: security@acme-prospect.com</div>
                    </div>
                  </div>
                  <div class="tl-email">
                    <div class="tl-email-head">
                      <b>Subject:</b> {subject_line}
                    </div>
                    <div class="tl-email-body">{rest}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # ---- Card C: slack ----
        with c_col:
            slack_body = build_slack_notification(answers)
            now = time.strftime("%I:%M %p")
            st.markdown(
                f"""
                <div class="tl-artifact">
                  <div class="tl-artifact-head">
                    <div class="tl-artifact-icon">💬</div>
                    <div>
                      <div class="tl-artifact-title">Slack Notification</div>
                      <div class="tl-artifact-sub">#deals-acme-prospect</div>
                    </div>
                  </div>
                  <div class="tl-slack">
                    <div class="tl-slack-row">
                      <div class="tl-slack-avatar">🛡️</div>
                      <div>
                        <div><span class="tl-slack-name">TrustLoop</span><span class="tl-slack-time">{now}</span></div>
                        <div class="tl-slack-body">{slack_body}</div>
                      </div>
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
