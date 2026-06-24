"""TrustLoop — Streamlit UI.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import io
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
)


# ---------- session-state helpers ----------

def _init_state() -> None:
    defaults: dict[str, object] = {
        "questions": [],
        "answers": [],
        "review_queue": [],
        "final_status": "idle",
        "run_complete": False,
        "selected_review_id": None,
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
    # Refresh queue
    st.session_state.review_queue = [
        a.question_id for a in answers if a.status == "needs_review"
    ]
    if not st.session_state.review_queue:
        st.session_state.final_status = "completed"


# ---------- header ----------

_init_state()

st.markdown(
    f"""
    <div style="display:flex;align-items:center;gap:12px;">
      <div style="font-size:38px;">🛡️</div>
      <div>
        <h1 style="margin:0;">TrustLoop</h1>
        <p style="margin:0;color:#6c757d;">
          AI-assisted security questionnaire automation for
          <b>{COMPANY_NAME}</b> · Deal: <b>{PROSPECT_NAME}</b>
        </p>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
mode_label = "LLM-augmented" if USE_LLM else "Deterministic offline"
st.caption(f"Mode: {mode_label} retrieval · Confidence threshold: 0.70")
st.divider()

tab_upload, tab_review, tab_artifacts = st.tabs(
    ["1 · Upload & Parse", "2 · Queue & Review", "3 · Artifact Hub"]
)


# ---------- Step 1 ----------

with tab_upload:
    st.subheader("Upload questionnaire")
    st.write(
        "Accepts an `.xlsx` workbook or a `.txt` file with one question per line."
    )

    uploaded = st.file_uploader(
        "Drop a questionnaire", type=["xlsx", "txt"], accept_multiple_files=False
    )
    pasted = st.text_area(
        "…or paste questions directly (one per line)",
        height=140,
        placeholder=(
            "Do you encrypt data at rest?\n"
            "Are you HIPAA certified?\n"
            "Where is customer data stored?"
        ),
    )

    parse_col, run_col = st.columns([1, 1])
    if parse_col.button("Parse questions", type="secondary"):
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
            st.success(f"Parsed {len(st.session_state.questions)} question(s).")
        else:
            st.warning("Nothing to parse yet — upload a file or paste questions.")

    if st.session_state.questions:
        df_q = pd.DataFrame([q.model_dump() for q in st.session_state.questions])
        st.dataframe(df_q, hide_index=True, use_container_width=True)

        if run_col.button("▶ Run multi-agent pipeline", type="primary"):
            with st.spinner("Researching, drafting, and verifying answers…"):
                # Reconstruct raw text from parsed questions so the graph re-parses
                # consistently (cheap; the intake step is deterministic).
                raw = "\n".join(q.text for q in st.session_state.questions)
                state = run_pipeline(raw)
            st.session_state.questions = list(state["questions"])
            st.session_state.answers = list(state["answers"])
            st.session_state.review_queue = list(state["review_queue"])
            st.session_state.final_status = state["final_status"]
            st.session_state.run_complete = state["final_status"] == "completed"
            st.success("Pipeline complete — switch to the Review tab.")


# ---------- Step 2 ----------

with tab_review:
    st.subheader("Queue & human review")

    answers: list[Answer] = st.session_state.answers
    if not answers:
        st.info("Run the pipeline from the Upload tab to populate the queue.")
    else:
        summary = summarize_run(answers)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total", summary.total)
        m2.metric("Auto-approved", summary.auto_approved)
        m3.metric("Awaiting review", summary.needs_review)
        m4.metric("Approved by human", summary.human_approved)

        if summary.needs_review == 0:
            st.success("Queue cleared — head to the Artifact Hub.")
        else:
            queue_ids = st.session_state.review_queue
            label_for = {
                qid: f"{qid} · {next(a.question_text for a in answers if a.question_id == qid)[:80]}"
                for qid in queue_ids
            }
            selected = st.selectbox(
                "Select an item to review",
                options=queue_ids,
                format_func=lambda qid: label_for.get(qid, qid),
                key="review_selector",
            )
            st.session_state.selected_review_id = selected
            current = _answer_by_id(selected)
            if current is not None:
                left, right = st.columns([1, 1])

                with left:
                    st.markdown("**Original question**")
                    st.write(current.question_text)

                    st.markdown("**Confidence**")
                    color = (
                        "#28a745" if current.confidence >= 0.70
                        else "#fd7e14" if current.confidence >= 0.40
                        else "#dc3545"
                    )
                    pct = int(current.confidence * 100)
                    st.markdown(
                        f"""
                        <div style="background:#e9ecef;border-radius:6px;height:18px;">
                          <div style="width:{pct}%;background:{color};height:18px;
                          border-radius:6px;color:white;text-align:right;padding-right:6px;
                          font-size:12px;line-height:18px;">
                            {pct}%
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    st.markdown("**Risk flags**")
                    if current.risk_flags:
                        for flag in current.risk_flags:
                            st.warning(flag)
                    else:
                        st.caption("No flags.")

                with right:
                    edited = st.text_area(
                        "Drafted answer (editable)",
                        value=current.draft,
                        height=240,
                        key=f"draft_{current.question_id}",
                    )
                    st.markdown("**Cited sources**")
                    if current.evidence:
                        for cite in current.evidence:
                            st.code(cite, language=None)
                    else:
                        st.caption("No grounded sources available.")

                    btn_a, btn_b, btn_c = st.columns(3)
                    if btn_a.button("✅ Approve", type="primary", key=f"approve_{current.question_id}"):
                        _update_answer(
                            current.model_copy(update={
                                "draft": edited,
                                "status": "human_approved",
                            })
                        )
                        st.rerun()
                    if btn_b.button("✏️ Edit & Approve", key=f"edit_{current.question_id}"):
                        _update_answer(
                            current.model_copy(update={
                                "draft": edited,
                                "status": "human_approved",
                            })
                        )
                        st.rerun()
                    if btn_c.button("❌ Reject", key=f"reject_{current.question_id}"):
                        _update_answer(
                            current.model_copy(update={
                                "draft": edited,
                                "status": "rejected",
                            })
                        )
                        st.rerun()


# ---------- Step 3 ----------

with tab_artifacts:
    st.subheader("Artifact hub")
    answers = st.session_state.answers
    if not answers:
        st.info("Run the pipeline to generate artifacts.")
    elif st.session_state.review_queue:
        st.warning(
            f"{len(st.session_state.review_queue)} item(s) still need review. "
            "Artifacts unlock once the queue is empty."
        )
    else:
        df = pd.DataFrame([a.model_dump() for a in answers])
        st.dataframe(df, hide_index=True, use_container_width=True)

        a, b, c = st.columns(3)

        with a:
            st.markdown("**Card A — Filled questionnaire (.xlsx)**")
            buf = io.BytesIO()
            # Re-export to memory so the download button can serve fresh bytes.
            tmp_path = export_workbook(answers, filename="trustloop_export.xlsx")
            buf.write(tmp_path.read_bytes())
            buf.seek(0)
            st.download_button(
                "Download workbook",
                data=buf,
                file_name="trustloop_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )

        with b:
            st.markdown("**Card B — Prospect email draft**")
            email_body = draft_prospect_email(answers)
            st.text_area("Email", value=email_body, height=260)
            st.caption("Copy with the icon in the top-right of the box.")

        with c:
            st.markdown("**Card C — Slack notification**")
            st.markdown(
                f"<div style='background:#1d1f21;color:#e6e6e6;padding:14px;"
                f"border-radius:8px;font-family:monospace;white-space:pre-wrap;'>"
                f"{build_slack_notification(answers)}</div>",
                unsafe_allow_html=True,
            )
