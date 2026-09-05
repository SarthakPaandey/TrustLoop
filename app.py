"""TrustLoop — Streamlit UI: marketing landing page plus questionnaire workspace."""

from __future__ import annotations

import contextlib
import io
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from actions import (
    build_slack_notification,
    draft_prospect_email,
    export_workbook,
    send_prospect_email,
    send_slack_notification,
    summarize_run,
)
from analytics import compute_analytics
from config import LLM_PROVIDER, USE_LLM
from graph import run_pipeline
from retrieval import ingest_document, list_documents
from storage import db

st.set_page_config(page_title="TrustLoop", page_icon="🔐", layout="wide", initial_sidebar_state="auto")


def _logo(size: int = 28, uid: str = "a") -> str:
    """Inline TrustLoop mark: shield + closed trust loop (SVG)."""
    gid = f"tlGrad_{uid}_{size}"
    return f"""<span class="tl-logo" style="width:{size}px;height:{size}px" aria-hidden="true">
<svg viewBox="0 0 40 40" width="{size}" height="{size}" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="{gid}" x1="6" y1="2" x2="34" y2="38" gradientUnits="userSpaceOnUse">
      <stop stop-color="#c4b5fd"/>
      <stop offset="0.45" stop-color="#818cf8"/>
      <stop offset="1" stop-color="#4f46e5"/>
    </linearGradient>
  </defs>
  <rect x="1" y="1" width="38" height="38" rx="11" fill="url(#{gid})"/>
  <rect x="1.5" y="1.5" width="37" height="37" rx="10.5" stroke="rgba(255,255,255,0.28)" stroke-width="1"/>
  <!-- shield -->
  <path d="M20 8.5L28.5 12.2V19.8C28.5 25.2 24.8 29.1 20 31.2C15.2 29.1 11.5 25.2 11.5 19.8V12.2L20 8.5Z"
        fill="rgba(255,255,255,0.14)" stroke="white" stroke-width="1.6" stroke-linejoin="round"/>
  <!-- trust loop (continuous circuit) -->
  <path d="M16.2 19.6c0-2.1 1.7-3.8 3.8-3.8 1.5 0 2.8.9 3.4 2.1"
        stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>
  <path d="M23.8 20.4c0 2.1-1.7 3.8-3.8 3.8-1.5 0-2.8-.9-3.4-2.1"
        stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>
  <path d="M22.6 16.2l1.1 1.8 2-.4" stroke="white" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  <path d="M17.4 23.8l-1.1-1.8-2 .4" stroke="white" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  <!-- center check -->
  <path d="M17.4 20.1l1.7 1.7 3.6-3.8" stroke="#ecfdf5" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
</svg></span>"""


def _brand_row(subtitle: str = "", size: int = 34, uid: str = "b") -> str:
    sub = f'<div class="side-brand-s">{subtitle}</div>' if subtitle else ""
    return f"""<div class="side-brand">
  {_logo(size, uid)}
  <div><div class="side-brand-t">Trust<span class="tl-accent">Loop</span></div>{sub}</div>
</div>"""


# ── Inline SVG icon set (stroke style, currentColor) ──
# Hand-authored 24x24 feather-style paths — no emoji, no webfont, no dependency.
_ICON_PATHS = {
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "shield-check": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 11.5 11 13.5 15 9.5"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "check-circle": '<path d="M22 11.1V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    "x": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "x-circle": '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
    "alert": '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "package": '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
    "chart": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    "upload": '<polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>',
    "download": '<polyline points="16 8 12 12 8 8"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>',
    "search": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
    "send": '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
    "book": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "home": '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "user": '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "eye": '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    "play": '<polygon points="5 3 19 12 5 21 5 3"/>',
    "clipboard": '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/>',
    "mail": '<path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><polyline points="22,6 12,13 2,6"/>',
    "message": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "edit": '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>',
    "flag": '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    "scale": '<path d="M12 3v18"/><path d="M5 7l-3 7a3.5 3.5 0 0 0 6 0L5 7z"/><path d="M19 7l-3 7a3.5 3.5 0 0 0 6 0l-3-7z"/><path d="M3 7h18"/>',
}


def ic(name: str, size: int = 16) -> str:
    """Inline SVG icon (stroke, currentColor) for custom HTML blocks."""
    path = _ICON_PATHS.get(name, _ICON_PATHS["alert"])
    return (
        f'<span class="tl-ic" aria-hidden="true">'
        f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" '
        f'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{path}</svg></span>'
    )


CSS_ENTERPRISE = r"""
<style>
/* ═══ ENTERPRISE THEME — flat surfaces, single accent, no glow ═══ */
.stApp{background:#070B14!important}
.landing{background:#070B14}
.stars,.nebula,.planet,.shoot,.space-grid,.app-glow1,.app-glow2{display:none!important}
.hero::before{display:none!important}
.tl-accent{background:none!important;-webkit-text-fill-color:#93A4F5!important;color:#93A4F5!important}
.hero-title .g1,.hero-title .g2,.hero-title .g3{background:none!important;-webkit-text-fill-color:#EDF1F7!important;color:#EDF1F7!important}
.tl-logo{box-shadow:none!important;filter:none!important}
.lnav{background:rgba(7,11,20,.94)!important;box-shadow:none!important}
.lnav-cta{background:#4F46E5!important;box-shadow:none!important;border:1px solid #4F46E5!important}
.btn-fill,.hero-btns a.btn-fill,.cta a.btn-fill{background:#4F46E5!important;box-shadow:none!important;border:1px solid #4F46E5!important}
.btn-fill:hover,.hero-btns a.btn-fill:hover{box-shadow:none!important;filter:brightness(1.1)!important}
.btn-ghost,.hero-btns a.btn-ghost{background:transparent!important;box-shadow:none!important}
.sec-wide{background:#090E18!important;border-top:1px solid #141D33!important;border-bottom:1px solid #141D33!important}
.cta{background:#0C1322!important;border:1px solid #1D2946!important;box-shadow:none!important}
.step,.feat,.hero-stat,.testimonial,.dstat,.acard,.kbcard,.rpanel,.conf-card,.pipe-shell,.dash-head,.dash-bar .chip,.nav-card,.mockup-wrap,.upload-zone,.arch-node,.split-path,.review-progress,.email-mock{
  background:#0C1322!important;border:1px solid #1D2946!important;box-shadow:none!important;
  backdrop-filter:none!important;-webkit-backdrop-filter:none!important}
.step::after{display:none!important}
.step:hover,.feat:hover,.testimonial:hover,.kbcard:hover,.dstat:hover,.dash-bar .chip:hover{transform:translateY(-2px)!important;border-color:#33436B!important;box-shadow:none!important;background:#0C1322!important}
.feat-ic{background:rgba(99,102,241,.1)!important;color:#A5B4FC}
.chip-ic .tl-ic,.feat-ic .tl-ic,.dstat-icon .tl-ic,.pipe-ic .tl-ic,.flag-icon .tl-ic,.cite .tl-ic{color:inherit}
.dstat-icon{color:#8FA2FF}
.pipe-ic{background:#111A2E!important}
.pipe-node.active .pipe-ic{animation:none!important}
.btn-approve button{background:#15803D!important;box-shadow:none!important;border:1px solid #15803D!important}
.btn-edit button{background:#B45309!important;box-shadow:none!important;border:1px solid #B45309!important}
.btn-reject button{background:#DC2626!important;box-shadow:none!important;border:1px solid #DC2626!important}
.btn-approve button:hover,.btn-edit button:hover,.btn-reject button:hover{box-shadow:none!important;filter:brightness(1.12)!important;transform:none!important}
.stButton>button[kind="primary"]{background:#4F46E5!important;box-shadow:none!important;border:1px solid #4F46E5!important}
.testimonial-av{font-weight:800!important;color:#C9D4F2!important;font-size:13px!important;background:rgba(99,102,241,.12)!important}
.testimonial-stars{color:#FBBF24!important}
.tl-ic{display:inline-flex;align-items:center;justify-content:center;line-height:0;vertical-align:-2px;flex-shrink:0}
.tl-ic svg{display:block}
.empty-ic,.summary-hero-ic,.upload-ic,.loading-ic,.autoemail-ic,.acard-ic,.info-banner-ic{color:#8FA2FF}
</style>
"""


# ── CSS ──
CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap');
html,body,[class*="css"]{font-family:'Inter',-apple-system,sans-serif;margin:0!important;padding:0!important;overflow-x:hidden;scroll-behavior:smooth}
#root,.stApp,.stBlock,[data-testid="stAppViewBlock"]>div{max-width:100%!important}
.element-container{padding:0!important;margin-bottom:12px!important}
.stMarkdown,.stTextElement,.stMarkdown>div,.stTextElement>div{padding:0!important;line-height:1.4!important}
.stVerticalBlock,.stHorizontalBlock,.stTabs,.stTab{padding:0!important;gap:12px!important}
header[data-testid="stHeader"],#MainMenu,footer,.stDeployButton{display:none!important}
.stApp{background:#06060F}
/* sidebar shown by default */

/* ═══ BRAND MARK ═══ */
.tl-logo{
  display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;
  border-radius:12px;line-height:0;
  box-shadow:0 4px 18px rgba(99,102,241,.42),0 0 0 1px rgba(255,255,255,.08);
  filter:drop-shadow(0 2px 8px rgba(79,70,229,.35))
}
.tl-logo svg{display:block;border-radius:11px}
.tl-accent{background:linear-gradient(135deg,#a5b4fc,#c084fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}

/* ═══ VARIABLES ═══ */
:root{
  --bg:#06060F; --bg2:#0A0A1A; --bg3:#0F0F24;
  --text:#f1f5f9; --text2:#a8b4c8; --text3:#6b7790;
  --primary:#6366f1; --primary-light:#a5b4fc; --primary-dark:#4f46e5;
  --accent:#a855f7; --accent2:#c084fc;
  --green:#34d399; --amber:#fbbf24; --red:#ef4444; --blue:#38bdf8;
  --glass:rgba(255,255,255,.035); --glass-border:rgba(255,255,255,.08);
  --glass-strong:rgba(15,23,42,.55);
  --radius:12px; --radius-sm:8px; --radius-lg:16px;
  --shadow-sm:0 2px 12px rgba(0,0,0,.25);
  --shadow-md:0 8px 32px rgba(0,0,0,.35);
  --shadow-glow:0 8px 40px rgba(99,102,241,.18);
}

/* ═══ LANDING NAV ═══ */
.lnav{
  position:fixed;top:0;left:0;right:0;z-index:1000;
  display:flex;align-items:center;justify-content:space-between;
  padding:0 40px;height:60px;
  background:rgba(6,6,15,.82);backdrop-filter:blur(28px) saturate(1.5);
  border-bottom:1px solid rgba(255,255,255,.07);
  box-shadow:0 4px 24px rgba(0,0,0,.25);
  transition:transform .3s ease,background .3s ease;
}
.lnav-brand{display:flex;align-items:center;gap:12px;font-size:18px;font-weight:800;color:var(--text);text-decoration:none;letter-spacing:-.03em}
.lnav-brand .tl-logo{box-shadow:0 4px 20px rgba(99,102,241,.5)}
.lnav-links{display:flex;align-items:center;gap:8px}
.lnav-links a{
  font-size:13px;font-weight:500;color:var(--text3);text-decoration:none;
  transition:all .2s;padding:8px 14px;border-radius:8px
}
.lnav-links a:hover{color:var(--text);background:rgba(255,255,255,.04)}
.lnav-cta{
  padding:10px 20px;border-radius:10px;font-size:13px;font-weight:700;
  background:linear-gradient(135deg,#818cf8,#6366f1 45%,#4f46e5);
  color:#ffffff!important;-webkit-text-fill-color:#ffffff!important;
  text-decoration:none!important;transition:all .2s;margin-left:8px;
  box-shadow:0 2px 16px rgba(99,102,241,.45),inset 0 1px 0 rgba(255,255,255,.2)
}
.lnav-cta:hover{transform:translateY(-1px);box-shadow:0 6px 24px rgba(99,102,241,.55);color:#ffffff!important;-webkit-text-fill-color:#ffffff!important}

/* ═══ LANDING ═══ */
.landing{position:relative;width:100%;min-height:100vh;overflow:hidden;background:var(--bg);padding-top:60px}
.landing *{box-sizing:border-box}

/* Starfield */
.stars{position:fixed;inset:0;pointer-events:none;z-index:0}
.star{position:absolute;border-radius:50%;background:#fff}

/* Nebula blobs */
.nebula{position:fixed;pointer-events:none;z-index:0;border-radius:50%;filter:blur(100px)}
.nebula.n1{width:700px;height:700px;background:rgba(99,102,241,.08);top:-15%;right:-8%;animation:nebDrift 25s ease-in-out infinite}
.nebula.n2{width:500px;height:500px;background:rgba(168,85,247,.06);bottom:5%;left:-8%;animation:nebDrift 30s ease-in-out infinite reverse}

@keyframes nebDrift{0%,100%{transform:translate(0,0)}50%{transform:translate(40px,-30px)}}

/* Grid overlay */
.space-grid{position:fixed;inset:0;pointer-events:none;z-index:0;
  background-image:linear-gradient(rgba(99,102,241,.02) 1px,transparent 1px),linear-gradient(90deg,rgba(99,102,241,.02) 1px,transparent 1px);
  background-size:60px 60px}

/* Planets */
.planet{position:fixed;pointer-events:none;z-index:0;border-radius:50%}
.planet.p1{width:350px;height:350px;top:10%;right:5%;background:radial-gradient(circle at 35% 35%,#1e3a5f 0%,#0f1f35 50%,#080e1a 100%);box-shadow:0 0 100px rgba(99,102,241,.12),inset -20px -10px 40px rgba(0,0,0,.5);animation:planetFloat 18s ease-in-out infinite}
@keyframes planetFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-14px)}}

@keyframes twinkle2{0%,100%{opacity:.3}50%{opacity:1}}
@keyframes twinkle3{0%,100%{opacity:.4}50%{opacity:.9}}
@keyframes twinkle4{0%,100%{opacity:.2}50%{opacity:.8}}
@keyframes twinkle5{0%,100%{opacity:.5}50%{opacity:1}}

/* Shooting stars */
.shoot{position:fixed;pointer-events:none;z-index:1;width:140px;height:1px;background:linear-gradient(90deg,rgba(255,255,255,.7),transparent);transform:rotate(-35deg);animation:shoot 5s linear infinite;opacity:0}
.shoot.s1{top:12%;left:8%;animation-delay:0s}
.shoot.s2{top:40%;left:55%;animation-delay:3s}
@keyframes shoot{0%{opacity:0;transform:rotate(-35deg) translateX(0)}4%{opacity:1}12%{opacity:1}20%{opacity:0;transform:rotate(-35deg) translateX(350px)}100%{opacity:0}}

/* Hero */
.hero{
  position:relative;min-height:calc(100vh - 56px);display:flex;flex-direction:column;justify-content:center;align-items:center;
  text-align:center;padding:60px 40px 40px;z-index:10
}
.hero::before{
  content:'';position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
  width:800px;height:800px;
  background:radial-gradient(circle,rgba(99,102,241,.04),transparent 60%);
  pointer-events:none;z-index:-1
}
.hero-inner{max-width:820px}
.hero-badge{
  display:inline-flex;align-items:center;gap:7px;padding:7px 18px;border-radius:999px;
  font-size:12px;font-weight:500;color:var(--primary-light);
  background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.18);
  backdrop-filter:blur(12px);margin-bottom:32px;animation:fadeUp .7s ease both
}
.hero-badge-dot{width:7px;height:7px;border-radius:50%;background:var(--primary-light);animation:pulse 2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
.hero-title{
  font-size:clamp(40px,6.5vw,72px);font-weight:900;letter-spacing:-.045em;line-height:1.02;
  color:var(--text);margin-bottom:22px;animation:fadeUp .7s ease .1s both
}
.hero-title .g1{background:linear-gradient(135deg,#818cf8,#6366f1,#4f46e5);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.hero-title .g2{background:linear-gradient(135deg,#c084fc,#a855f7,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.hero-title .g3{background:linear-gradient(135deg,#38bdf8,#0ea5e3);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.hero-sub{
  font-size:17px;color:var(--text2);line-height:1.7;max-width:580px;margin:0 auto 38px;animation:fadeUp .7s ease .2s both
}
.hero-btns{display:flex;gap:16px;justify-content:center;flex-wrap:wrap;animation:fadeUp .7s ease .3s both;margin-top:4px}

/* Hero CTAs — high contrast so Streamlit link styles cannot wash them out */
.btn,
a.btn,
.hero-btns a,
.cta a.btn{
  padding:16px 32px!important;border-radius:12px!important;font-size:15px!important;font-weight:700!important;
  cursor:pointer;transition:all .25s ease!important;text-decoration:none!important;
  display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:8px!important;
  position:relative;overflow:hidden;line-height:1.2!important;letter-spacing:.01em;
  border:none!important;box-sizing:border-box!important
}
a.btn:visited,a.btn:active,a.btn:focus{
  text-decoration:none!important;outline:none
}

/* Primary — solid bright purple, pure white label */
.btn-fill,
a.btn-fill,
.hero-btns a.btn-fill,
.cta a.btn-fill{
  background:linear-gradient(135deg,#a5b4fc 0%,#818cf8 25%,#6366f1 60%,#4f46e5 100%)!important;
  color:#ffffff!important;-webkit-text-fill-color:#ffffff!important;
  border:1px solid rgba(255,255,255,.22)!important;
  box-shadow:
    0 4px 28px rgba(99,102,241,.55),
    0 0 0 1px rgba(129,140,248,.35),
    inset 0 1px 0 rgba(255,255,255,.28)!important
}
.btn-fill:hover,
a.btn-fill:hover{
  transform:translateY(-2px)!important;
  color:#ffffff!important;-webkit-text-fill-color:#ffffff!important;
  box-shadow:
    0 10px 40px rgba(99,102,241,.65),
    0 0 0 1px rgba(165,180,252,.5),
    inset 0 1px 0 rgba(255,255,255,.35)!important;
  filter:brightness(1.06)
}

/* Secondary — clear glass pill, bright border + white text */
.btn-ghost,
a.btn-ghost,
.hero-btns a.btn-ghost{
  background:rgba(255,255,255,.1)!important;
  color:#f1f5f9!important;-webkit-text-fill-color:#f1f5f9!important;
  border:1.5px solid rgba(165,180,252,.55)!important;
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
  box-shadow:0 2px 16px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.1)!important
}
.btn-ghost:hover,
a.btn-ghost:hover{
  background:rgba(129,140,248,.18)!important;
  border-color:rgba(199,210,254,.85)!important;
  color:#ffffff!important;-webkit-text-fill-color:#ffffff!important;
  transform:translateY(-1px)!important;
  box-shadow:0 6px 24px rgba(99,102,241,.25)!important
}
.hero-scroll{
  position:absolute;bottom:28px;left:50%;transform:translateX(-50%);
  display:flex;flex-direction:column;align-items:center;gap:6px;
  color:var(--text3);font-size:10px;letter-spacing:.08em;text-transform:uppercase;
  animation:fadeUp .7s ease .6s both;cursor:pointer;z-index:10
}
.hero-scroll-arr{width:16px;height:16px;border-right:1.5px solid var(--text3);border-bottom:1.5px solid var(--text3);transform:rotate(45deg);animation:scrollBounce 2s ease-in-out infinite}
@keyframes scrollBounce{0%,100%{transform:rotate(45deg) translateY(0)}50%{transform:rotate(45deg) translateY(6px)}}

/* Stats */
.hero-stats{
  display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:52px;
  animation:fadeUp .7s ease .4s both;max-width:760px;width:100%
}
@media (max-width:720px){.hero-stats{grid-template-columns:repeat(2,1fr)}}
.hero-stat{
  text-align:center;padding:24px 16px;border-radius:16px;
  background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.02));
  border:1px solid var(--glass-border);
  backdrop-filter:blur(12px);transition:all .3s ease;
  box-shadow:var(--shadow-sm)
}
.hero-stat:hover{background:rgba(255,255,255,.06);transform:translateY(-3px);border-color:rgba(129,140,248,.25);box-shadow:var(--shadow-glow)}
.hero-stat-val{font-size:32px;font-weight:900;letter-spacing:-.03em;line-height:1}
.hero-stat-val.v1{color:var(--primary-light)}
.hero-stat-val.v2{color:var(--accent2)}
.hero-stat-val.v3{color:var(--green)}
.hero-stat-val.v4{color:var(--amber)}
.hero-stat-lbl{font-size:11.5px;color:var(--text3);margin-top:8px;font-weight:600;letter-spacing:.02em}

@keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}

/* Sections */
.sec{position:relative;z-index:5;padding:88px 48px;max-width:1120px;margin:0 auto}
.sec-wide{
  background:linear-gradient(180deg,rgba(15,15,36,.55),rgba(6,6,15,.9));
  max-width:100%;padding-left:calc((100% - 1072px)/2);padding-right:calc((100% - 1072px)/2);
  border-top:1px solid rgba(255,255,255,.04);border-bottom:1px solid rgba(255,255,255,.04)
}
.sec-tag{
  display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;
  color:var(--primary-light);padding:6px 14px;border-radius:999px;
  background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.22);margin-bottom:18px
}
.sec-title{font-size:clamp(28px,3.8vw,42px);font-weight:900;letter-spacing:-.035em;color:var(--text);margin-bottom:14px;line-height:1.12}
.sec-desc{font-size:15.5px;color:var(--text2);line-height:1.7;max-width:560px;margin-bottom:40px}

/* Steps */
.steps-wrapper{position:relative;padding:10px 0}
.steps-connector{position:absolute;top:46px;left:calc(12.5% + 36px);right:calc(12.5% + 36px);height:2px;
  background:linear-gradient(90deg,var(--primary),var(--accent),var(--amber),var(--green));
  opacity:.15;z-index:0}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;position:relative;z-index:1}
.step{
  padding:28px 22px 26px;border-radius:18px;
  background:linear-gradient(165deg,rgba(255,255,255,.05),rgba(255,255,255,.015));
  border:1px solid var(--glass-border);
  backdrop-filter:blur(10px);transition:all .35s ease;position:relative;overflow:hidden;
  box-shadow:var(--shadow-sm)
}
.step::after{content:'';position:absolute;inset:0;border-radius:18px;padding:1px;
  background:linear-gradient(135deg,transparent 40%,rgba(99,102,241,.2));
  -webkit-mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);
  mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);
  -webkit-mask-composite:xor;mask-composite:exclude;opacity:0;transition:opacity .4s}
.step:hover::after{opacity:1}
.step:hover{transform:translateY(-5px);box-shadow:var(--shadow-md);border-color:rgba(129,140,248,.2)}
.step-n{
  width:42px;height:42px;border-radius:12px;display:flex;align-items:center;justify-content:center;
  font-size:13px;font-weight:800;margin-bottom:16px;position:relative;z-index:1
}
.step-n.n1{background:rgba(99,102,241,.16);color:var(--primary-light);box-shadow:0 0 16px rgba(99,102,241,.12)}
.step-n.n2{background:rgba(168,85,247,.16);color:var(--accent2);box-shadow:0 0 16px rgba(168,85,247,.12)}
.step-n.n3{background:rgba(251,191,36,.14);color:var(--amber);box-shadow:0 0 16px rgba(251,191,36,.1)}
.step-n.n4{background:rgba(52,211,153,.14);color:var(--green);box-shadow:0 0 16px rgba(52,211,153,.1)}
.step h3{font-size:15.5px;font-weight:700;color:var(--text);margin-bottom:8px}
.step p{font-size:13px;color:var(--text2);line-height:1.6}

/* Features */
.feats{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
@media (max-width:900px){.feats{grid-template-columns:1fr 1fr}}
@media (max-width:560px){.feats{grid-template-columns:1fr}}
.feat{
  padding:28px 24px;border-radius:16px;
  background:linear-gradient(165deg,rgba(255,255,255,.05),rgba(255,255,255,.015));
  border:1px solid var(--glass-border);
  backdrop-filter:blur(10px);transition:all .3s ease;position:relative;overflow:hidden;
  box-shadow:var(--shadow-sm)
}
.feat:hover{border-color:rgba(99,102,241,.28);background:rgba(255,255,255,.05);transform:translateY(-3px);box-shadow:var(--shadow-glow)}
.feat-ic{
  width:48px;height:48px;border-radius:14px;display:flex;align-items:center;justify-content:center;
  font-size:22px;margin-bottom:16px;transition:all .3s ease
}
.feat:hover .feat-ic{transform:scale(1.08) translateY(-2px)}
.feat-ic.i1{background:rgba(99,102,241,.14)}
.feat-ic.i2{background:rgba(168,85,247,.14)}
.feat-ic.i3{background:rgba(52,211,153,.14)}
.feat-ic.i4{background:rgba(251,191,36,.14)}
.feat-ic.i5{background:rgba(244,114,182,.14)}
.feat-ic.i6{background:rgba(14,165,233,.14)}
.feat h3{font-size:15px;font-weight:700;color:var(--text);margin-bottom:8px}
.feat p{font-size:13px;color:var(--text2);line-height:1.6}

/* Dashboard mockup */
.mockup-wrap{
  background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(15,23,42,.5));
  border:1px solid rgba(255,255,255,.1);border-radius:20px;overflow:hidden;
  backdrop-filter:blur(12px);margin-top:30px;box-shadow:var(--shadow-md),0 0 0 1px rgba(99,102,241,.06)
}
.mockup-bar{display:flex;align-items:center;gap:8px;padding:14px 18px;border-bottom:1px solid var(--glass-border)}
.mockup-dot{width:10px;height:10px;border-radius:50%}
.mockup-dot.md1{background:#ef4444}
.mockup-dot.md2{background:#fbbf24}
.mockup-dot.md3{background:#34d399}
.mockup-tab{display:flex;gap:6px;margin-left:20px}
.mockup-tab-item{padding:4px 12px;border-radius:5px;font-size:10px;font-weight:500;color:var(--text3);background:rgba(255,255,255,.03)}
.mockup-tab-item.active{color:var(--primary-light);background:rgba(99,102,241,.08)}
.mockup-body{display:grid;grid-template-columns:1fr 1.8fr;gap:0;min-height:280px}
.mockup-left{border-right:1px solid var(--glass-border);padding:14px}
.mockup-left-item{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:7px;font-size:11px;color:var(--text3);transition:all .15s}
.mockup-left-item:hover{background:var(--glass)}
.mockup-left-item.active{background:rgba(99,102,241,.06);color:var(--text)}
.mockup-left-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.mockup-left-dot.green{background:var(--green)}
.mockup-left-dot.yellow{background:var(--amber)}
.mockup-left-dot.blue{background:var(--blue)}
.mockup-right{padding:16px}
.mockup-right-q{font-size:13px;font-weight:600;color:var(--text);margin-bottom:10px;line-height:1.4}
.mockup-right-conf{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.mockup-right-gauge{width:48px;height:48px;border-radius:50%;border:3px solid var(--green);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--green)}
.mockup-right-bar{flex:1;height:4px;border-radius:999px;background:rgba(255,255,255,.04)}
.mockup-right-fill{height:100%;width:85%;border-radius:999px;background:linear-gradient(90deg,var(--green),var(--primary))}
.mockup-right-flag{display:flex;align-items:center;gap:6px;padding:6px 10px;border-radius:6px;font-size:10.5px;background:rgba(251,191,36,.05);border:1px solid rgba(251,191,36,.1);color:var(--amber);margin-bottom:8px}
.mockup-right-edit{padding:8px 10px;border-radius:6px;background:rgba(15,23,42,.5);border:1px solid var(--glass-border);font-size:11px;color:var(--text3);line-height:1.4;min-height:50px}
.mockup-right-acts{display:flex;gap:6px;margin-top:10px}
.mockup-right-btn{padding:7px 14px;border-radius:8px;font-size:11px;font-weight:700;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.05);color:var(--text2)}
.mockup-right-btn.green{background:rgba(52,211,153,.14);color:var(--green);border-color:rgba(52,211,153,.25)}
.mockup-right-btn.red{background:rgba(239,68,68,.12);color:var(--red);border-color:rgba(239,68,68,.22)}

/* Testimonials */
.testimonials{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:10px}
.testimonial{
  padding:24px 22px;border-radius:16px;
  background:var(--glass);border:1px solid var(--glass-border);
  backdrop-filter:blur(8px);transition:all .3s ease
}
.testimonial:hover{transform:translateY(-3px);border-color:rgba(99,102,241,.1)}
.testimonial-stars{color:var(--amber);font-size:13px;margin-bottom:10px}
.testimonial-text{font-size:12.5px;color:var(--text2);line-height:1.6;margin-bottom:16px;font-style:italic}
.testimonial-author{display:flex;align-items:center;gap:10px}
.testimonial-av{width:34px;height:34px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px}
.testimonial-name{font-size:12px;font-weight:600;color:var(--text)}
.testimonial-role{font-size:10px;color:var(--text3)}

/* CTA */
.cta{
  text-align:center;padding:88px 40px 72px;position:relative;z-index:5;
  margin:20px 32px 0;border-radius:24px;
  background:linear-gradient(160deg,rgba(99,102,241,.12),rgba(168,85,247,.06) 50%,rgba(6,6,15,.4));
  border:1px solid rgba(129,140,248,.2);
  box-shadow:var(--shadow-glow)
}
.cta h2{font-size:clamp(26px,3.2vw,36px);font-weight:900;color:var(--text);margin-bottom:14px;letter-spacing:-.03em}
.cta p{font-size:15px;color:var(--text2);margin-bottom:32px;max-width:460px;margin-left:auto;margin-right:auto;line-height:1.6}

/* Footer */
.foot{
  border-top:1px solid var(--glass-border);padding:28px 48px;
  display:flex;justify-content:space-between;align-items:center;color:var(--text3);
  font-size:12px;position:relative;z-index:5;background:rgba(6,6,15,.95);margin-top:40px
}

/* ═══ APP ═══ */
.app-bg{
  position:fixed;inset:0;pointer-events:none;z-index:0;
  background-image:linear-gradient(rgba(99,102,241,.012) 1px,transparent 1px),linear-gradient(90deg,rgba(99,102,241,.012) 1px,transparent 1px);
  background-size:60px 60px
}
/* Ambient glow spots on content */
.app-glow1,.app-glow2{
  position:fixed;pointer-events:none;z-index:0;border-radius:50%;filter:blur(80px)
}
.app-glow1{
  width:400px;height:400px;background:rgba(99,102,241,.04);top:20%;right:10%;
  animation:glowDrift 20s ease-in-out infinite
}
.app-glow2{
  width:300px;height:300px;background:rgba(14,165,233,.03);bottom:30%;left:5%;
  animation:glowDrift 25s ease-in-out infinite reverse
}
@keyframes glowDrift{0%,100%{transform:translate(0,0)}50%{transform:translate(20px,-15px)}}

.appbar{
  position:sticky;top:0;z-index:100;
  display:flex;align-items:center;justify-content:space-between;
  padding:0 24px;height:52px;
  background:rgba(6,6,15,.88);backdrop-filter:blur(24px) saturate(1.5);
  border-bottom:1px solid rgba(255,255,255,.08);
  box-shadow:0 4px 20px rgba(0,0,0,.2);margin-bottom:4px
}
.appbar-brand{display:flex;align-items:center;gap:11px;font-size:16px;font-weight:800;color:var(--text);text-decoration:none;letter-spacing:-.03em}
.appbar-brand-name{display:flex;flex-direction:column;line-height:1.1;gap:2px}
.appbar-brand-name b{font-size:15px;font-weight:800}
.appbar-brand-name span{font-size:10px;font-weight:600;color:var(--text3);letter-spacing:.04em;text-transform:uppercase}
.appbar-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.appbar-badge{
  display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:999px;
  font-size:11px;font-weight:700;letter-spacing:.02em;
  background:rgba(99,102,241,.12);color:var(--primary-light);border:1px solid rgba(99,102,241,.28)
}
.appbar-badge.running{background:rgba(251,191,36,.1);color:var(--amber);border-color:rgba(251,191,36,.28);animation:pulse 1.6s ease-in-out infinite}
.appbar-meta{
  display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:8px;
  font-size:11px;font-weight:600;color:var(--text2);background:rgba(255,255,255,.03);
  border:1px solid rgba(255,255,255,.07)
}
.appbar-home{padding:5px 12px;border-radius:8px;cursor:pointer;font-size:11px;font-weight:600;color:var(--text2);background:var(--glass);border:1px solid var(--glass-border);transition:all .2s}

/* Dashboard command header */
.dash-head{
  max-width:1100px;margin:6px auto 12px!important;padding:18px 20px 16px;
  background:linear-gradient(135deg,rgba(99,102,241,.1),rgba(168,85,247,.05) 40%,rgba(15,23,42,.4));
  border:1px solid rgba(129,140,248,.18);border-radius:18px;
  box-shadow:var(--shadow-sm);position:relative;z-index:5;overflow:hidden
}
.dash-head::before{
  content:'';position:absolute;top:-40%;right:-5%;width:220px;height:220px;
  background:radial-gradient(circle,rgba(129,140,248,.16),transparent 70%);pointer-events:none
}
.dash-head-row{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;position:relative;z-index:1}
.dash-head-title{font-size:18px;font-weight:800;color:var(--text);letter-spacing:-.03em;margin-bottom:4px}
.dash-head-sub{font-size:12.5px;color:var(--text2);line-height:1.5;max-width:520px}
.dash-head-pills{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.dash-pill{
  display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:999px;
  font-size:11px;font-weight:700;border:1px solid rgba(255,255,255,.08);
  background:rgba(6,6,15,.45);color:var(--text2)
}
.dash-pill strong{color:var(--text);font-weight:800}
.dash-pill.on{color:var(--green);border-color:rgba(52,211,153,.25);background:rgba(52,211,153,.08)}
.dash-pill.warn{color:var(--amber);border-color:rgba(251,191,36,.25);background:rgba(251,191,36,.08)}
.dash-progress{margin-top:14px;position:relative;z-index:1}
.dash-progress-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.dash-progress-lbl{font-size:10.5px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.08em}
.dash-progress-val{font-size:12px;font-weight:700;color:var(--primary-light)}
.dash-progress-bar{height:7px;background:rgba(255,255,255,.05);border-radius:999px;overflow:hidden;border:1px solid rgba(255,255,255,.04)}
.dash-progress-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,#34d399,#818cf8,#a855f7);box-shadow:0 0 12px rgba(129,140,248,.35);transition:width .5s ease}

/* Pipeline shell */
.pipe-shell{
  max-width:1100px;margin:14px auto 10px!important;padding:20px 22px 16px;
  background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(15,23,42,.4));
  border:1px solid rgba(255,255,255,.09);border-radius:18px;
  box-shadow:var(--shadow-sm);position:relative;z-index:5
}
.pipe-shell-title{
  display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;
  margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,.06)
}
.pipe-shell-title h3{margin:0;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--text3)}
.pipe-shell-title>span{font-size:11px;font-weight:600;color:var(--primary-light);background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.2);padding:4px 10px;border-radius:999px}
/* Streamlit injects heading anchor links into our custom h3 cards — never pill them */
.pipe-shell-title [data-testid="stHeaderActionElements"]{display:none!important}
.step [data-testid="stHeaderActionElements"],.feat [data-testid="stHeaderActionElements"]{display:none!important}
.pipe-strip{
  display:flex;align-items:center;justify-content:center;gap:0;
  max-width:720px;margin:0 auto!important;
  padding:4px 8px 6px;position:relative;z-index:5
}
.pipe-node{display:flex;flex-direction:column;align-items:center;gap:8px;position:relative;flex-shrink:0}
.pipe-ic{
  width:52px;height:52px;border-radius:15px;display:flex;align-items:center;justify-content:center;
  font-size:22px;border:1.5px solid rgba(255,255,255,.1);background:rgba(15,23,42,.65);
  transition:all .4s ease;position:relative;box-shadow:inset 0 1px 0 rgba(255,255,255,.05)
}
.pipe-node.active .pipe-ic{
  border-color:rgba(129,140,248,.55);background:rgba(99,102,241,.14);
  box-shadow:0 0 22px rgba(99,102,241,.22);animation:pipePulse 2s ease-in-out infinite
}
.pipe-node.done .pipe-ic{
  border-color:rgba(52,211,153,.4);background:rgba(52,211,153,.12);
  box-shadow:0 0 14px rgba(52,211,153,.12)
}
.pipe-lbl{font-size:11.5px;font-weight:700;color:var(--text3);transition:color .3s;text-align:center;white-space:nowrap;letter-spacing:0.02em}
.pipe-node.active .pipe-lbl{color:var(--primary-light)}
.pipe-node.done .pipe-lbl{color:var(--green)}
.pipe-seg{width:40px;height:3px;background:rgba(255,255,255,.06);margin:0 4px;margin-bottom:20px;transition:all .5s ease;border-radius:999px;flex-shrink:0}
.pipe-seg.active{background:linear-gradient(90deg,var(--green),var(--primary-light));box-shadow:0 0 10px rgba(99,102,241,.2)}
.pipe-seg.done{background:var(--green)}
@keyframes pipePulse{0%,100%{box-shadow:0 0 14px rgba(99,102,241,.15)}50%{box-shadow:0 0 26px rgba(99,102,241,.3)}}

.pipe-stage-info{
  text-align:center;font-size:12px;color:var(--text2);margin-top:10px;padding:8px 16px 0;
  animation:fadeUp .3s ease both;border-top:1px solid rgba(255,255,255,.05)
}
.pipe-stage-info strong{color:var(--text);font-weight:600}

/* Dashboard KPI grid */
.dash-bar{
  display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;
  max-width:1100px;margin:0 auto 16px!important;padding:0 0 4px;
  position:relative;z-index:5
}
@media (max-width:960px){.dash-bar{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:520px){.dash-bar{grid-template-columns:1fr}}
.dash-bar .chip{
  display:flex;align-items:center;gap:12px;padding:14px 16px;border-radius:14px;
  font-size:12px;font-weight:600;min-width:0;
  background:linear-gradient(165deg,rgba(255,255,255,.055),rgba(15,23,42,.45));
  border:1px solid var(--glass-border);box-shadow:var(--shadow-sm);
  transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease
}
.dash-bar .chip:hover{transform:translateY(-2px);box-shadow:var(--shadow-md)}
.dash-bar .chip-ic{
  width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;
  font-size:18px;flex-shrink:0;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08)
}
.dash-bar .chip > span:last-child{display:flex;flex-direction:column;gap:2px;font-size:11px;font-weight:600;opacity:.9;min-width:0}
.dash-bar .chip .chip-val{font-size:20px;font-weight:900;letter-spacing:-.03em;line-height:1.1;opacity:1;color:inherit}
.dash-bar .chip.ct{color:var(--text2);border-color:rgba(255,255,255,.1)}
.dash-bar .chip.ct .chip-ic{background:rgba(148,163,184,.1);color:var(--text)}
.dash-bar .chip.co{color:var(--green);border-color:rgba(52,211,153,.22);background:linear-gradient(165deg,rgba(52,211,153,.1),rgba(15,23,42,.4))}
.dash-bar .chip.co .chip-ic{background:rgba(52,211,153,.12)}
.dash-bar .chip.cw{color:var(--amber);border-color:rgba(251,191,36,.24);background:linear-gradient(165deg,rgba(251,191,36,.1),rgba(15,23,42,.4))}
.dash-bar .chip.cw .chip-ic{background:rgba(251,191,36,.12)}
.dash-bar .chip.ci{color:var(--blue);border-color:rgba(14,165,233,.24);background:linear-gradient(165deg,rgba(14,165,233,.1),rgba(15,23,42,.4))}
.dash-bar .chip.ci .chip-ic{background:rgba(14,165,233,.12)}
.dash-bar .chip.cr{color:var(--red);border-color:rgba(239,68,68,.22);background:linear-gradient(165deg,rgba(239,68,68,.1),rgba(15,23,42,.4))}
.dash-bar .chip.cr .chip-ic{background:rgba(239,68,68,.12)}
.dash-bar .chip.ready{color:var(--primary-light)!important;border-color:rgba(99,102,241,.3)!important;background:linear-gradient(165deg,rgba(99,102,241,.14),rgba(15,23,42,.4))!important}
.dash-bar .chip.ready .chip-ic{background:rgba(99,102,241,.16)}

/* Empty dashboard welcome */
.dash-welcome{
  max-width:1100px;margin:0 auto 18px;display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:12px;position:relative;z-index:5
}
@media (max-width:900px){.dash-welcome{grid-template-columns:1fr}}
.dash-welcome-card{
  padding:18px 18px 16px;border-radius:16px;
  background:linear-gradient(165deg,rgba(255,255,255,.05),rgba(15,23,42,.4));
  border:1px solid rgba(255,255,255,.09);box-shadow:var(--shadow-sm)
}
.dash-welcome-card.primary{
  background:linear-gradient(145deg,rgba(99,102,241,.16),rgba(168,85,247,.08) 50%,rgba(15,23,42,.45));
  border-color:rgba(129,140,248,.28)
}
.dash-welcome-ic{font-size:22px;margin-bottom:10px}
.dash-welcome-t{font-size:14px;font-weight:800;color:var(--text);margin-bottom:6px;letter-spacing:-.02em}
.dash-welcome-s{font-size:12px;color:var(--text2);line-height:1.55}

/* Review diff box */
.diffbox{margin-top:12px;border:1px solid rgba(99,102,241,.14);border-radius:10px;background:rgba(99,102,241,.03);padding:12px 14px;animation:aFade .25s ease}
.diffbox-h{font-size:11px;font-weight:800;color:var(--primary-light);letter-spacing:.04em;text-transform:uppercase;margin-bottom:10px}
.diff-cols{display:flex;gap:10px;flex-wrap:wrap}
.diff-col{flex:1;min-width:240px;border-radius:8px;padding:10px 12px}
.diff-del{background:rgba(239,68,68,.06);border:1px solid rgba(239,68,68,.18)}
.diff-add{background:rgba(52,211,153,.06);border:1px solid rgba(52,211,153,.18)}
.diff-lbl{font-size:9.5px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}
.diff-del .diff-lbl{color:#f87171}
.diff-add .diff-lbl{color:var(--green)}
.diff-body{font-size:11.5px;line-height:1.55;color:var(--text2);white-space:pre-wrap;word-break:break-word}

/* Upload tab */
.upload-zone{
  text-align:center;padding:48px 28px 36px;margin-bottom:8px;
  background:linear-gradient(165deg,rgba(99,102,241,.08),rgba(255,255,255,.02));
  border:1px dashed rgba(129,140,248,.35);border-radius:20px;
  box-shadow:var(--shadow-sm)
}
.upload-ic{font-size:48px;margin-bottom:14px;filter:drop-shadow(0 4px 12px rgba(99,102,241,.25))}
.upload-h{font-size:20px;font-weight:800;color:var(--text);margin-bottom:8px;letter-spacing:-.02em}
.upload-sub{font-size:13.5px;color:var(--text2);margin-bottom:8px;line-height:1.55;max-width:420px;margin-left:auto;margin-right:auto}

/* Question browser */
.qbrowser{display:flex;flex-direction:column;gap:10px}
.qbrowser-filter{display:flex;gap:8px;flex-wrap:wrap;padding:12px 0}
.qbrowser-filter-btn{
  padding:5px 14px;border-radius:999px;font-size:11px;font-weight:500;border:1px solid var(--glass-border);
  background:transparent;color:var(--text3);cursor:pointer;transition:all .2s
}
.qbrowser-filter-btn:hover{color:var(--text);border-color:rgba(255,255,255,.1)}
.qbrowser-filter-btn.active{background:rgba(99,102,241,.08);color:var(--primary-light);border-color:rgba(99,102,241,.2)}
.qlist{display:flex;flex-direction:column;gap:4px}
.qrow{
  display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:12px;
  background:linear-gradient(90deg,rgba(255,255,255,.03),rgba(255,255,255,.015));
  border:1px solid var(--glass-border);
  transition:all .18s ease;cursor:default
}
.qrow:hover{background:rgba(255,255,255,.05);border-color:rgba(129,140,248,.2);transform:translateX(2px)}
.qrow-n{font-size:11px;font-weight:700;color:var(--text3);min-width:24px;font-family:'JetBrains Mono',monospace}
.qrow-t{flex:1;font-size:13px;color:var(--text);line-height:1.4}
.qrow-c{padding:3px 8px;border-radius:5px;font-size:9.5px;font-weight:600;white-space:nowrap}
.qrow-c.technical{background:rgba(99,102,241,.08);color:var(--primary-light)}
.qrow-c.certification{background:rgba(168,85,247,.08);color:var(--accent2)}
.qrow-c.legal{background:rgba(239,68,68,.08);color:#fca5a5}
.qrow-c.data-privacy{background:rgba(251,191,36,.08);color:#fcd34d}
.qrow-c.general{background:rgba(255,255,255,.04);color:var(--text3)}
.qrow-status{padding:3px 7px;border-radius:4px;font-size:9px;font-weight:600;white-space:nowrap}
.qrow-status.auto{background:rgba(52,211,153,.08);color:var(--green)}
.qrow-status.review{background:rgba(251,191,36,.08);color:var(--amber)}

/* Review split panel */
.review-split{display:flex;gap:0;margin-top:4px;min-height:500px}
.review-list{
  width:340px;min-width:340px;border-right:1px solid var(--glass-border);
  padding:12px 10px 12px 0;overflow-y:auto;max-height:calc(100vh - 260px)
}
.review-list-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;padding:0 4px}
.review-list-title{font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.06em}
.review-list-count{font-size:11px;color:var(--text2);font-weight:500}
.review-detail{flex:1;padding:0 0 0 18px;overflow-y:auto;max-height:calc(100vh - 260px)}
.review-progress{background:var(--glass);border:1px solid var(--glass-border);border-radius:9px;padding:12px 14px;margin-bottom:14px}
.review-progress-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.review-progress-lbl{font-size:10.5px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.05em}
.review-progress-val{font-size:13px;font-weight:700;color:var(--text)}
.review-progress-bar{height:4px;background:rgba(255,255,255,.03);border-radius:999px;overflow:hidden}
.review-progress-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--green),var(--primary-light));transition:width .4s ease}

/* Question item in review list */
.qitem{
  display:flex;align-items:center;gap:9px;padding:9px 11px;border-radius:8px;
  cursor:pointer;transition:all .15s ease;border:1px solid transparent;margin-bottom:3px
}
.qitem:hover{background:rgba(255,255,255,.02);border-color:var(--glass-border)}
.qitem.selected{background:rgba(99,102,241,.06);border-color:rgba(99,102,241,.15)}
.qitem-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-top:2px}
.qitem-dot.green{background:var(--green);box-shadow:0 0 6px rgba(52,211,153,.3)}
.qitem-dot.yellow{background:var(--amber);box-shadow:0 0 6px rgba(251,191,36,.3)}
.qitem-dot.blue{background:var(--blue);box-shadow:0 0 6px rgba(56,189,248,.3)}
.qitem-dot.red{background:var(--red);box-shadow:0 0 6px rgba(239,68,68,.3)}
.qitem-num{font-size:10px;font-weight:500;color:var(--text3);font-family:'JetBrains Mono',monospace;min-width:16px}
.qitem-text{flex:1;font-size:11px;color:var(--text2);line-height:1.3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.qitem-cat{font-size:9px;padding:2px 6px;border-radius:3px;font-weight:500}

/* Review detail panel */
.rpanel{
  animation:fadeUp .2s ease both;
  background:rgba(15,23,42,.4);
  border:1px solid rgba(255,255,255,.05);
  border-radius:16px;
  padding:24px;
  box-shadow:0 12px 40px rgba(99,102,241,.04)
}
.rpanel-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.rpanel-id{font-size:11px;font-weight:600;color:var(--text3);font-family:'JetBrains Mono',monospace;letter-spacing:.05em}
.rpanel-cat{padding:4px 10px;border-radius:6px;font-size:10px;font-weight:700;letter-spacing:.03em;text-transform:uppercase}
.rpanel-q{
  font-size:15px;font-weight:700;color:var(--text);line-height:1.5;margin-bottom:20px;
  padding:16px 20px;background:rgba(99,102,241,.03);border:1px solid rgba(99,102,241,.08);
  border-radius:12px;border-left:4px solid var(--primary);
  box-shadow:inset 0 2px 4px rgba(0,0,0,.1)
}

/* Confidence display */
.conf-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}
.conf-card{
  background:rgba(255,255,255,.015);
  border:1px solid rgba(255,255,255,.03);
  border-radius:12px;
  padding:16px 18px;
  box-shadow:0 4px 12px rgba(0,0,0,.1)
}
.conf-card-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.conf-card-lbl{font-size:10px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.08em}
.conf-card-val{font-size:22px;font-weight:900;letter-spacing:-.03em}
.conf-card-bar{height:6px;background:rgba(255,255,255,.03);border-radius:999px;overflow:hidden}
.conf-card-fill{height:100%;border-radius:999px;transition:width .5s ease}

/* Circular confidence */
.conf-circle-wrap{display:flex;flex-direction:column;align-items:center;justify-content:center}
.conf-circle{
  width:72px;height:72px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  font-size:18px;font-weight:800;position:relative
}
.conf-circle svg circle{
  fill:none;stroke-width:5;cx:36;cy:36;r:30
}

/* Flags */
.flags{display:flex;flex-direction:column;gap:8px;margin-bottom:18px}
.flag{
  display:flex;align-items:center;gap:8px;padding:10px 14px;border-radius:8px;
  font-size:12px;line-height:1.5;transition:all .15s ease
}
.flag.fw{background:rgba(251,191,36,.04);border:1px solid rgba(251,191,36,.12);border-left:4px solid var(--amber);color:#fde047}
.flag.fd{background:rgba(239,68,68,.04);border:1px solid rgba(239,68,68,.12);border-left:4px solid var(--red);color:#fca5a5}
.flag.fi{background:rgba(14,165,233,.04);border:1px solid rgba(14,165,233,.12);border-left:4px solid var(--blue);color:#bae6fd}
.flag.fp{background:rgba(168,85,247,.04);border:1px solid rgba(168,85,247,.12);border-left:4px solid var(--accent2);color:#ddd6fe}
.flag-icon{font-size:14px;width:18px;text-align:center;flex-shrink:0}

/* Citations */
.cites{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:18px}
.cite{
  padding:5px 12px;border-radius:8px;font-size:11px;font-weight:500;
  background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.05);
  color:var(--text2);font-family:'JetBrains Mono',monospace;transition:all .2s;
  box-shadow:0 2px 4px rgba(0,0,0,.05)
}
.cite:hover{background:rgba(99,102,241,.06);color:var(--primary-light);border-color:rgba(99,102,241,.15)}

/* Answer editor */
.answer-section{margin-bottom:16px}
.answer-section-lbl{font-size:11px;font-weight:700;color:var(--text3);margin-bottom:8px;text-transform:uppercase;letter-spacing:.08em}

/* Navigation card layout */
.nav-card {
  background:rgba(15,23,42,.3);
  border:1px solid rgba(255,255,255,.04);
  border-radius:12px;
  padding:18px 20px;
  backdrop-filter:blur(12px);
  box-shadow:0 4px 24px rgba(0,0,0,.2);
  margin-bottom:20px!important
}

/* Custom styled action buttons */
.btn-approve button {
  background:linear-gradient(135deg,#10b981,#059669)!important;
  color:white!important;border:none!important;
  box-shadow:0 4px 14px rgba(16, 185, 129, 0.2)!important;
  transition:all .2s ease!important;
  font-weight:700!important
}
.btn-approve button:hover {
  transform:translateY(-1.5px)!important;
  box-shadow:0 6px 20px rgba(16, 185, 129, 0.35)!important;
  filter:brightness(1.05)!important
}

.btn-edit button {
  background:linear-gradient(135deg,#f59e0b,#d97706)!important;
  color:white!important;border:none!important;
  box-shadow:0 4px 14px rgba(245, 158, 11, 0.15)!important;
  transition:all .2s ease!important;
  font-weight:700!important
}
.btn-edit button:hover {
  transform:translateY(-1.5px)!important;
  box-shadow:0 6px 20px rgba(245, 158, 11, 0.25)!important;
  filter:brightness(1.05)!important
}

.btn-reject button {
  background:linear-gradient(135deg,#ef4444,#dc2626)!important;
  color:white!important;border:none!important;
  box-shadow:0 4px 14px rgba(239, 68, 68, 0.2)!important;
  transition:all .2s ease!important;
  font-weight:700!important
}
.btn-reject button:hover {
  transform:translateY(-1.5px)!important;
  box-shadow:0 6px 20px rgba(239, 68, 68, 0.3)!important;
  filter:brightness(1.05)!important
}

.btn-approve-all button {
  background:linear-gradient(135deg,rgba(16, 185, 129, 0.08),rgba(5, 150, 105, 0.08))!important;
  color:#34d399!important;
  border:1px solid rgba(16, 185, 129, 0.25)!important;
  transition:all .2s ease!important;
  font-weight:700!important;
  font-size:12.5px!important
}
.btn-approve-all button:hover {
  background:linear-gradient(135deg,rgba(16, 185, 129, 0.15),rgba(5, 150, 105, 0.15))!important;
  border-color:rgba(16, 185, 129, 0.45)!important;
  transform:translateY(-1.5px)!important
}

/* Deliver tab */
.dgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
.dstat{
  background:var(--glass);border:1px solid var(--glass-border);border-radius:12px;
  padding:18px 14px;text-align:center;transition:all .2s ease
}
.dstat:hover{transform:translateY(-1px);border-color:rgba(255,255,255,.06)}
.dstat-icon{font-size:22px;margin-bottom:6px}
.dstat-k{font-size:10px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
.dstat-v{font-size:26px;font-weight:900;margin-top:2px;letter-spacing:-.02em}

.acard{background:var(--glass);border:1px solid var(--glass-border);border-radius:14px;padding:20px;height:100%}
.acard-head{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.acard-ic{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}
.acard-t{font-size:14px;font-weight:700;color:var(--text)}
.acard-sub{font-size:11px;color:var(--text3);margin-top:1px}

.email-mock{background:rgba(15,23,42,.5);border:1px solid var(--glass-border);border-radius:10px;overflow:hidden}
.email-bar{
  background:rgba(255,255,255,.02);padding:8px 12px;border-bottom:1px solid var(--glass-border);
  font-size:11px;color:var(--text3)
}
.email-bar b{color:var(--text2)}
.email-body{padding:12px;font-size:12px;color:var(--text2);white-space:pre-wrap;line-height:1.6;max-height:220px;overflow-y:auto}

.slack-mock{background:#1A1D21;border-radius:10px;padding:14px}
.slack-row{display:flex;gap:10px}
.slack-av{
  width:36px;height:36px;border-radius:8px;background:linear-gradient(135deg,var(--primary),var(--primary-dark));
  display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0
}
.slack-name{color:#FFF;font-weight:700;font-size:12px}
.slack-time{color:#616876;font-size:10px;margin-left:5px}
.slack-body{font-size:12px;color:#D1D2D3;line-height:1.5;white-space:pre-wrap;margin-top:3px}

.autoemail{
  background:linear-gradient(135deg,rgba(52,211,153,.06),rgba(99,102,241,.06));
  border:1px solid rgba(52,211,153,.15);border-radius:12px;padding:14px 18px;
  display:flex;align-items:center;gap:10px;margin-bottom:18px
}
.autoemail-ic{width:36px;height:36px;border-radius:9px;background:rgba(52,211,153,.1);display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}
.autoemail-t{font-size:13px;color:var(--green);font-weight:600}
.autoemail-sub{font-size:11px;color:var(--text3);margin-top:2px}

/* KB */
.kbgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:16px}
.kbcard{
  background:var(--glass);border:1px solid var(--glass-border);border-radius:10px;
  padding:14px 16px;transition:all .2s ease
}
.kbcard:hover{border-color:rgba(99,102,241,.1);transform:translateY(-1px)}
.kbcard-name{font-size:12px;font-weight:600;color:var(--primary-light);font-family:'JetBrains Mono',monospace;margin-bottom:4px}
.kbcard-title{font-size:12px;font-weight:600;color:var(--text);margin-bottom:3px}
.kbcard-desc{font-size:11px;color:var(--text3);line-height:1.45}
.kbcard-tags{display:flex;gap:4px;margin-top:6px;flex-wrap:wrap}
.kbcard-tag{padding:2px 7px;border-radius:4px;font-size:9px;font-weight:500;background:rgba(99,102,241,.06);color:var(--primary-light)}

/* Empty & Loading */
.empty{text-align:center;padding:60px 20px}
.empty-ic{font-size:48px;margin-bottom:12px;opacity:.4}
.empty-t{font-size:16px;font-weight:600;color:var(--text2);margin-bottom:6px}
.empty-sub{font-size:12px;color:var(--text3)}

.loading{text-align:center;padding:48px}
.loading-ic{font-size:40px;margin-bottom:12px;animation:spin 2s linear infinite}
@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
.loading-t{font-size:15px;font-weight:600;color:var(--primary-light);margin-bottom:4px}
.loading-sub{font-size:11.5px;color:var(--text3)}

/* Info banner */
.info-banner{
  background:linear-gradient(135deg,rgba(99,102,241,.06),rgba(168,85,247,.04));
  border:1px solid rgba(99,102,241,.15);border-radius:12px;padding:16px 18px;
  margin-bottom:16px;display:flex;align-items:center;gap:12px
}
.info-banner-ic{width:38px;height:38px;border-radius:9px;background:rgba(99,102,241,.1);display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}
.info-banner-content{flex:1}
.info-banner-title{font-size:13px;font-weight:700;color:var(--text);margin-bottom:2px}
.info-banner-sub{font-size:11px;color:var(--text3)}

/* Streamlit overrides */
.stTabs [data-baseweb="tab-list"]{
  gap:4px;background:rgba(15,23,42,.55);padding:5px;border-radius:14px;
  border:1px solid rgba(255,255,255,.08);margin-bottom:18px;
  box-shadow:var(--shadow-sm)
}
.stTabs [data-baseweb="tab"]{
  background:transparent!important;color:var(--text3)!important;border-radius:10px!important;
  padding:10px 18px!important;font-weight:600!important;font-size:13px!important;
  border:none!important;transition:all .18s!important
}
.stTabs [data-baseweb="tab"]:hover{color:var(--text)!important;background:rgba(255,255,255,.04)!important}
.stTabs [aria-selected="true"]{
  color:#fff!important;background:linear-gradient(135deg,rgba(99,102,241,.35),rgba(99,102,241,.18))!important;
  box-shadow:0 2px 14px rgba(99,102,241,.2)!important;border:1px solid rgba(129,140,248,.25)!important
}
.stButton>button{
  border-radius:10px!important;font-weight:700!important;font-size:13px!important;
  transition:all .18s!important;min-height:40px!important;
  background:rgba(255,255,255,.05)!important;color:var(--text)!important;
  border:1px solid rgba(255,255,255,.12)!important;
  box-shadow:0 2px 8px rgba(0,0,0,.15)!important
}
.stButton>button:hover{
  transform:translateY(-1px)!important;border-color:rgba(165,180,252,.35)!important;
  background:rgba(255,255,255,.08)!important;color:#fff!important
}
.stButton>button[kind="primary"]{
  background:linear-gradient(135deg,#818cf8,#6366f1 50%,#4f46e5)!important;
  color:#fff!important;border:1px solid rgba(255,255,255,.2)!important;
  box-shadow:0 4px 18px rgba(99,102,241,.4)!important
}
.stButton>button[kind="primary"]:hover{
  filter:brightness(1.06)!important;box-shadow:0 6px 24px rgba(99,102,241,.5)!important
}
.stTextArea textarea,.stTextInput input{
  background:rgba(15,23,42,.6)!important;border:1px solid rgba(255,255,255,.1)!important;
  border-radius:12px!important;color:var(--text)!important;font-size:13px!important;
  line-height:1.55!important;caret-color:var(--primary-light)!important;
  padding:12px 14px!important
}
.stTextArea textarea:focus,.stTextInput input:focus{
  border-color:rgba(129,140,248,.45)!important;
  box-shadow:0 0 0 3px rgba(99,102,241,.12)!important
}
.stSelectbox [data-baseweb="select"]{
  background:rgba(15,23,42,.6)!important;border-color:rgba(255,255,255,.1)!important;
  border-radius:10px!important;font-size:13px!important;min-height:40px!important
}
[data-testid="stFileUploaderDropzone"]{
  background:rgba(15,23,42,.5)!important;border:1.5px dashed rgba(129,140,248,.3)!important;
  border-radius:16px!important;transition:all .2s!important;padding:28px 16px!important
}
[data-testid="stFileUploaderDropzone"]:hover{
  border-color:rgba(129,140,248,.55)!important;background:rgba(99,102,241,.06)!important
}
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,rgba(10,10,26,.98),rgba(6,6,15,.98))!important;
  border-right:1px solid rgba(255,255,255,.08)!important;
  backdrop-filter:blur(16px)!important
}
.stSidebar .stButton>button{font-size:12.5px!important;padding:10px 14px!important;min-height:42px!important}
.stSidebar [data-testid="stMarkdownContainer"] p{color:var(--text2)!important;font-size:13px!important;line-height:1.5!important}
.stAlert{border-radius:12px!important;border:1px solid rgba(255,255,255,.08)!important}

/* Sidebar brand block */
.side-brand{
  display:flex;align-items:center;gap:12px;padding:6px 2px 16px;margin-bottom:6px;
  border-bottom:1px solid rgba(255,255,255,.08)
}
.side-brand-t{font-size:16px;font-weight:800;color:var(--text);letter-spacing:-.03em;line-height:1.15}
.side-brand-s{font-size:11.5px;color:var(--text3);margin-top:3px;font-weight:500;line-height:1.35}
.side-sec{
  font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;
  color:var(--text3);margin:14px 0 8px;padding:0 2px
}
.side-summary{
  background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);
  border-radius:12px;padding:12px 14px;margin:8px 0 4px
}
.side-summary-row{
  display:flex;justify-content:space-between;align-items:center;
  font-size:12.5px;line-height:1.9
}
.side-summary-row span:first-child{color:var(--text3)}
.side-summary-row span:last-child{font-weight:700;color:var(--text)}

/* Tab page headers */
.tab-head{margin:4px 0 16px}
.tab-head-t{font-size:18px;font-weight:800;color:var(--text);letter-spacing:-.02em;margin-bottom:4px}
.tab-head-s{font-size:13px;color:var(--text2);line-height:1.5}

/* Workspace nav (replaces cluttered default tabs) */
.ws-nav{
  display:flex;gap:8px;flex-wrap:wrap;padding:6px;margin:4px auto 18px;max-width:1100px;
  background:rgba(15,23,42,.55);border:1px solid rgba(255,255,255,.08);border-radius:14px;
  box-shadow:var(--shadow-sm);position:relative;z-index:5
}
.ws-nav-item{
  flex:1;min-width:120px;text-align:center;padding:10px 12px;border-radius:10px;
  font-size:12.5px;font-weight:700;color:var(--text3);border:1px solid transparent
}
.ws-nav-item.active{
  color:#fff;background:linear-gradient(135deg,rgba(99,102,241,.4),rgba(99,102,241,.2));
  border-color:rgba(129,140,248,.3);box-shadow:0 2px 14px rgba(99,102,241,.2)
}
.ws-nav-item .ws-badge{
  display:inline-block;margin-left:6px;padding:1px 7px;border-radius:999px;font-size:10px;
  background:rgba(251,191,36,.15);color:var(--amber);border:1px solid rgba(251,191,36,.25)
}

/* Compact summary (upload after pipeline) */
.summary-hero{
  max-width:900px;margin:0 auto 18px;padding:28px 28px 24px;text-align:center;
  background:linear-gradient(145deg,rgba(99,102,241,.12),rgba(168,85,247,.06) 50%,rgba(15,23,42,.45));
  border:1px solid rgba(129,140,248,.22);border-radius:20px;box-shadow:var(--shadow-md)
}
.summary-hero-ic{font-size:36px;margin-bottom:10px}
.summary-hero-t{font-size:22px;font-weight:900;color:var(--text);letter-spacing:-.03em;margin-bottom:8px}
.summary-hero-s{font-size:14px;color:var(--text2);line-height:1.55;max-width:520px;margin:0 auto 18px}
.summary-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:18px 0 8px}
@media (max-width:640px){.summary-stats{grid-template-columns:1fr}}
.summary-stat{
  padding:16px 12px;border-radius:14px;background:rgba(6,6,15,.4);
  border:1px solid rgba(255,255,255,.08)
}
.summary-stat-v{font-size:26px;font-weight:900;letter-spacing:-.03em;line-height:1}
.summary-stat-l{font-size:11px;color:var(--text3);font-weight:600;margin-top:6px}
.cat-pills{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin:16px 0 4px}
.cat-pill{
  padding:6px 12px;border-radius:999px;font-size:11.5px;font-weight:700;
  border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.03);color:var(--text2)
}
.flagged-preview{max-width:900px;margin:16px auto 0;text-align:left}
.flagged-preview-h{
  font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;
  letter-spacing:.08em;margin-bottom:10px
}
.flagged-row{
  display:flex;align-items:center;gap:12px;padding:12px 14px;border-radius:12px;margin-bottom:8px;
  background:rgba(251,191,36,.05);border:1px solid rgba(251,191,36,.14)
}
.flagged-row .fr-n{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text3);min-width:28px}
.flagged-row .fr-t{flex:1;font-size:13px;color:var(--text);font-weight:600;line-height:1.35}
.flagged-row .fr-flag{font-size:10.5px;color:var(--amber);font-weight:700;white-space:nowrap}

/* Guided review focus card */
.guide-bar{
  max-width:820px;margin:0 auto 16px;padding:16px 18px;border-radius:16px;
  background:linear-gradient(165deg,rgba(255,255,255,.05),rgba(15,23,42,.45));
  border:1px solid rgba(255,255,255,.09)
}
.guide-bar-top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px}
.guide-bar-title{font-size:13px;font-weight:800;color:var(--text);letter-spacing:-.01em}
.guide-bar-meta{font-size:12px;font-weight:700;color:var(--primary-light)}
.guide-steps{display:flex;gap:6px;margin-top:10px;flex-wrap:wrap}
.guide-step{
  width:28px;height:6px;border-radius:999px;background:rgba(255,255,255,.08)
}
.guide-step.done{background:var(--green)}
.guide-step.active{background:linear-gradient(90deg,var(--amber),#f59e0b);box-shadow:0 0 10px rgba(251,191,36,.35)}
.guide-hint{
  max-width:820px;margin:0 auto 14px;text-align:center;font-size:12.5px;color:var(--text2)
}
.guide-hint strong{color:var(--text)}
.review-focus{max-width:820px;margin:0 auto}

/* ═══ ARCHITECTURE DIAGRAM ═══ */
.arch-flow {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 12px;
  margin-top: 36px;
  margin-bottom: 24px;
}
@media (max-width: 992px) {
  .arch-flow {
    flex-direction: column;
    align-items: center;
  }
  .arch-arrow {
    transform: rotate(90deg);
    height: 40px;
    width: 20px !important;
    margin: 10px 0;
  }
}
.arch-node {
  flex: 1;
  background: var(--glass);
  border: 1px solid var(--glass-border);
  border-radius: 16px;
  padding: 22px;
  backdrop-filter: blur(8px);
  position: relative;
  transition: all .3s ease;
  display: flex;
  flex-direction: column;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
}
.arch-node:hover {
  border-color: rgba(99,102,241,0.25);
  box-shadow: 0 8px 32px rgba(99,102,241,0.12);
  transform: translateY(-2px);
}
.arch-badge {
  align-self: flex-start;
  font-size: 9px;
  font-weight: 700;
  color: var(--primary-light);
  background: rgba(99,102,241,0.08);
  border: 1px solid rgba(99,102,241,0.18);
  padding: 3px 8px;
  border-radius: 5px;
  text-transform: uppercase;
  margin-bottom: 12px;
  letter-spacing: 0.05em;
}
.arch-node-title {
  font-size: 15px;
  font-weight: 800;
  color: var(--text);
  margin-bottom: 8px;
}
.arch-node-desc {
  font-size: 12px;
  color: var(--text2);
  line-height: 1.4;
  margin-bottom: 16px;
  flex-grow: 1;
}
.arch-node-details {
  border-top: 1px solid rgba(255,255,255,0.05);
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.arch-node-details div {
  font-size: 10.5px;
  color: var(--text2);
  line-height: 1.3;
}
.arch-node-details span {
  font-weight: 700;
  color: var(--text3);
}

/* Specific Node Styles */
.router-node {
  border-color: rgba(168,85,247,0.15);
}
.router-node:hover {
  border-color: rgba(168,85,247,0.35);
  box-shadow: 0 8px 32px rgba(168,85,247,0.12);
}
.router-badge {
  color: var(--accent2);
  background: rgba(168,85,247,0.08);
  border-color: rgba(168,85,247,0.18);
}
.reviewer-node {
  border-color: rgba(251,191,36,0.15);
}
.reviewer-node:hover {
  border-color: rgba(251,191,36,0.35);
  box-shadow: 0 8px 32px rgba(251,191,36,0.12);
}
.reviewer-node .arch-badge {
  color: var(--amber);
  background: rgba(251,191,36,0.08);
  border-color: rgba(251,191,36,0.18);
}
.delivery-node {
  border-color: rgba(52,211,153,0.15);
}
.delivery-node:hover {
  border-color: rgba(52,211,153,0.35);
  box-shadow: 0 8px 32px rgba(52,211,153,0.12);
}
.delivery-badge {
  color: var(--green);
  background: rgba(52,211,153,0.08);
  border-color: rgba(52,211,153,0.18);
}

/* Connectors */
.arch-arrow {
  width: 40px;
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.arch-arrow svg {
  width: 100%;
  height: 20px;
  overflow: visible;
}
.flow-line {
  animation: travel-line 1.2s linear infinite;
}
.flow-line-accent {
  animation: travel-line 1.2s linear infinite reverse;
}
.flow-line-amber {
  animation: travel-line 1.5s linear infinite;
}
.flow-line-green {
  animation: travel-line 1.5s linear infinite;
}
.flow-line-gray {
  animation: travel-line 2s linear infinite;
}
@keyframes travel-line {
  to {
    stroke-dashoffset: -16;
  }
}

/* Split path sections */
.arch-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  max-width: 900px;
  margin: 12px auto 24px;
}
@media (max-width: 768px) {
  .arch-split {
    grid-template-columns: 1fr;
    gap: 16px;
  }
}
.split-path {
  background: rgba(255,255,255,0.01);
  border: 1px solid rgba(255,255,255,0.03);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.path-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.path-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 5px;
  text-transform: uppercase;
}
.path-badge.green {
  color: var(--green);
  background: rgba(52,211,153,0.08);
  border: 1px solid rgba(52,211,153,0.18);
}
.path-badge.amber {
  color: var(--amber);
  background: rgba(251,191,36,0.08);
  border: 1px solid rgba(251,191,36,0.18);
}
.path-desc {
  font-size: 11px;
  color: var(--text3);
}

/* Outputs Row */
.arch-outputs {
  display: flex;
  align-items: stretch;
  justify-content: center;
  gap: 16px;
  max-width: 760px;
  margin: 0 auto 36px;
}
@media (max-width: 768px) {
  .arch-outputs {
    flex-direction: column;
    align-items: center;
  }
  .small-arrow {
    transform: rotate(90deg);
    height: 30px;
    width: 20px !important;
  }
}
.arch-outputs .arch-node {
  max-width: 320px;
  width: 100%;
}
.small-arrow {
  width: 30px;
  display: flex;
  align-items: center;
}

/* ═══ MOBILE / RESPONSIVE ═══
   Phones (≤640px): single-column everything, stacked Streamlit columns,
   swipeable pipeline strip. Tablets (≤900px): two-column grids. */
@media (max-width:900px){
  .steps{grid-template-columns:1fr 1fr}
  .steps-connector{display:none}
  .testimonials{grid-template-columns:1fr 1fr}
  .dgrid{grid-template-columns:repeat(2,1fr)}
  .mockup-body{grid-template-columns:1fr}
  .mockup-left{border-right:none;border-bottom:1px solid var(--glass-border)}
}
@media (max-width:768px){
  .lnav{padding:0 16px;max-width:100vw}
  .lnav-links a:not(.lnav-cta){display:none}
  .lnav-brand{font-size:16px}
  .hero{padding:44px 20px 30px;min-height:unset}
  .hero-sub{font-size:15px}
  .sec{padding:56px 20px}
  .sec-wide{padding-left:20px!important;padding-right:20px!important}
  .cta{margin:16px 12px 0;padding:52px 24px 44px}
  .foot{flex-direction:column;gap:10px;text-align:center;padding:24px 20px}
  .dash-head{padding:16px}
  .pipe-shell{padding:16px 14px}
  .pipe-strip{overflow-x:auto;justify-content:flex-start;max-width:100%;-webkit-overflow-scrolling:touch}
  .pipe-ic{width:44px;height:44px;font-size:19px;border-radius:13px}
  .pipe-seg{width:22px}
  .pipe-lbl{font-size:10.5px}
  .review-split{flex-direction:column;min-height:unset}
  .review-list{width:100%;min-width:0;border-right:none;border-bottom:1px solid var(--glass-border);padding:0 0 12px;max-height:290px}
  .review-detail{padding:16px 0 0;max-height:none}
  .rpanel{padding:20px 18px}
  .appbar{padding:6px 12px;height:auto;min-height:52px;flex-wrap:wrap;row-gap:6px}
  .qrow{flex-wrap:wrap;row-gap:8px}
  .cite{overflow-wrap:anywhere}
  .rpanel-q{overflow-wrap:break-word}
  .mockup-tab{flex-wrap:wrap}
  .stTabs [data-baseweb="tab-list"]{overflow-x:auto;max-width:100%}
  .stTabs [data-baseweb="tab"]{padding:10px 12px!important;font-size:12px!important;white-space:nowrap}
  [data-testid="stHorizontalBlock"]{flex-wrap:wrap}
}
@media (max-width:640px){
  /* Stack every Streamlit column layout: nav buttons, centered CTAs,
     3-up action rows and card grids all degrade to full-width rows.
     Centering spacers ([1,2,1]) collapse to near-zero-height rows. */
  [data-testid="stHorizontalBlock"]{flex-direction:column!important;align-items:stretch!important}
  [data-testid="column"]{width:100%!important;flex:1 1 100%!important;min-width:0!important}
  .steps{grid-template-columns:1fr}
  .testimonials{grid-template-columns:1fr}
  .dgrid{grid-template-columns:1fr}
  .kbgrid{grid-template-columns:1fr}
  .conf-grid{grid-template-columns:1fr}
  .hero-btns{flex-direction:column;align-items:stretch}
  .hero-btns .btn,.hero-btns a.btn{width:100%!important}
  .hero-stats{gap:10px}
  .diff-cols{flex-direction:column}
  .upload-zone{padding:36px 18px 28px}
  .empty{padding:44px 16px}
}
</style>
"""

CSS_LANDING = r"""
<style>
[data-testid="stSidebar"] { display: none !important; }
[data-testid="stSidebarCollapseButton"] { display: none !important; }
.stMain { margin-left: 0 !important; padding-left: 0 !important; width: 100% !important; }
.block-container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; }

/* Streamlit often recolors markdown <a> tags — force CTA contrast on landing */
.stMarkdown a.btn,
.stMarkdown a.btn-fill,
.stMarkdown a.btn-ghost,
.stMarkdown a.lnav-cta,
a.btn, a.btn-fill, a.btn-ghost, a.lnav-cta {
  text-decoration: none !important;
}
.stMarkdown a.btn-fill,
a.btn-fill {
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
}
.stMarkdown a.btn-ghost,
a.btn-ghost {
  color: #f1f5f9 !important;
  -webkit-text-fill-color: #f1f5f9 !important;
}
.stMarkdown a.lnav-cta,
a.lnav-cta {
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
}
</style>
"""

CSS_APP = r"""
<style>
.block-container { padding: 12px 28px 36px 28px !important; max-width: 100% !important; }

.stVerticalBlock { gap: 14px !important; }
.stHorizontalBlock { gap: 14px !important; }
.element-container { margin-bottom: 10px !important; }

.stMarkdown, .stMarkdown > div { line-height: 1.55 !important; }
.stMarkdown p { margin-top: 4px !important; margin-bottom: 6px !important; }
.stMarkdown h3 {
  font-size: 1.15rem !important; font-weight: 800 !important;
  letter-spacing: -0.02em !important; color: #f1f5f9 !important;
  margin: 4px 0 8px !important;
}

.rpanel {
  padding: 26px 28px !important;
  margin-bottom: 18px !important;
  background: linear-gradient(165deg, rgba(255,255,255,.04), rgba(15,23,42,.45)) !important;
  border: 1px solid rgba(255,255,255,.08) !important;
  box-shadow: 0 8px 28px rgba(0,0,0,.25) !important;
}
.rpanel-q {
  margin-top: 10px !important;
  margin-bottom: 8px !important;
  padding: 18px 20px !important;
  line-height: 1.55 !important;
  font-size: 16px !important;
}

.conf-grid {
  gap: 14px !important;
  margin-top: 12px !important;
  margin-bottom: 18px !important;
}
.conf-card {
  padding: 18px 20px !important;
  background: linear-gradient(165deg, rgba(255,255,255,.04), rgba(255,255,255,.015)) !important;
  border-radius: 14px !important;
}
.conf-card-top { margin-bottom: 10px !important; }

.flags { gap: 10px !important; margin-top: 8px !important; margin-bottom: 16px !important; }
.flag { padding: 12px 16px !important; line-height: 1.55 !important; border-radius: 10px !important; }

.cites { gap: 8px !important; margin-top: 8px !important; margin-bottom: 16px !important; }
.cite { padding: 8px 14px !important; border-radius: 10px !important; }

.answer-section { margin-top: 16px !important; margin-bottom: 10px !important; }
.answer-section-lbl {
  margin-bottom: 8px !important; font-size: 12px !important;
  letter-spacing: .08em !important; color: #6b7790 !important;
}
[data-testid="stTextArea"] { margin-top: 4px !important; margin-bottom: 16px !important; }

.btn-approve, .btn-edit, .btn-reject { margin-top: 4px !important; }
.btn-approve button, .btn-edit button, .btn-reject button {
  min-height: 44px !important; font-size: 13.5px !important; border-radius: 11px !important;
}

.nav-card {
  background: linear-gradient(165deg, rgba(255,255,255,.04), rgba(15,23,42,.4)) !important;
  border: 1px solid rgba(255,255,255,.08) !important;
  border-radius: 14px !important;
  padding: 18px 20px !important;
  box-shadow: 0 4px 20px rgba(0,0,0,.2) !important;
}

.dgrid { gap: 14px !important; margin-bottom: 22px !important; }
.dstat {
  padding: 22px 16px !important; border-radius: 16px !important;
  background: linear-gradient(165deg, rgba(255,255,255,.05), rgba(255,255,255,.015)) !important;
  border: 1px solid rgba(255,255,255,.09) !important;
  box-shadow: 0 4px 16px rgba(0,0,0,.2) !important;
}
.dstat:hover { transform: translateY(-2px) !important; border-color: rgba(129,140,248,.25) !important; }
.acard {
  background: linear-gradient(165deg, rgba(255,255,255,.04), rgba(15,23,42,.4)) !important;
  border: 1px solid rgba(255,255,255,.09) !important;
  border-radius: 16px !important;
  padding: 20px !important;
  box-shadow: 0 4px 20px rgba(0,0,0,.2) !important;
}
.kbcard {
  padding: 16px 18px !important; border-radius: 14px !important;
  background: linear-gradient(165deg, rgba(255,255,255,.04), rgba(255,255,255,.015)) !important;
  border: 1px solid rgba(255,255,255,.08) !important;
}
.kbcard:hover { border-color: rgba(129,140,248,.3) !important; transform: translateY(-2px) !important; }
.loading {
  background: linear-gradient(165deg, rgba(99,102,241,.08), rgba(255,255,255,.02));
  border: 1px solid rgba(129,140,248,.2); border-radius: 18px;
  margin: 8px 0 16px; padding: 40px 24px !important;
}
.info-banner {
  border-radius: 14px !important; padding: 16px 18px !important;
  margin-bottom: 16px !important;
}
.empty { padding: 72px 24px !important; }
.empty-ic { opacity: .55 !important; }

/* Decorative planet sits behind workspace cards — keep it faint so text stays crisp. */
.planet.p1 { opacity: .38 !important; }

/* Mobile surfaces: tighter page padding, roomier stacked cards. */
@media (max-width:640px){
  .block-container { padding: 12px 14px 32px 14px !important; }
  .rpanel { padding: 18px 16px !important; }
  .rpanel-q { font-size: 14.5px !important; padding: 14px 16px !important; }
  .nav-card { padding: 14px 16px !important; }
  .dstat { padding: 18px 14px !important; }
  .acard { padding: 16px !important; }
  .empty { padding: 44px 16px !important; }
}
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


# ── STATE ──
def _init():
    for k, v in {
        "page": "landing", "questions": [], "answers": [], "review_queue": [],
        "final_status": "idle", "run_complete": False,
        "step": 0, "pipe_stage": -1, "demo": False, "email_sent": False,
        "balloons_shown": False, "total_review_items": 0,
        "auto_run": False, "auto_run_start": 0, "pipeline_done": False,
        "workspace_view": "upload", "rsel": None, "show_all_questions": False,
        "just_finished_pipeline": False, "demo_prompt": False,
        "run_id": None, "original_drafts": {},
    }.items():
        st.session_state.setdefault(k, v)


def _remember_originals():
    """Snapshot the pristine drafts so the review panel can show a real diff."""
    for a in st.session_state.answers:
        st.session_state.original_drafts.setdefault(a.question_id, a.draft)


def _reviewer() -> str:
    return (st.session_state.get("reviewer_name") or "").strip() or "anonymous_reviewer"


def _ans(qid):
    for a in st.session_state.answers:
        if a.question_id == qid:
            return a
    return None


def _upd(ans):
    """Apply review decision, persist it to the audit trail, auto-advance."""
    lst = st.session_state.answers
    for i, a in enumerate(lst):
        if a.question_id == ans.question_id:
            lst[i] = ans
            break
    action = "review_reject" if ans.status == "rejected" else "review_approve"
    db.record_decision(
        run_id=st.session_state.get("run_id"),
        question_id=ans.question_id,
        actor=_reviewer(),
        action=action,
        final_text=ans.draft,
        new_status=ans.status,
    )
    st.session_state.review_queue = [a.question_id for a in lst if a.status == "needs_review"]
    if st.session_state.review_queue:
        # Always land on the next item — user does not pick manually
        st.session_state.rsel = st.session_state.review_queue[0]
        st.session_state.workspace_view = "review"
    else:
        st.session_state.rsel = None
        st.session_state.final_status = "completed"
        st.session_state.pipe_stage = 4
        st.session_state.workspace_view = "deliver"
        s = summarize_run(lst)
        db.complete_run(st.session_state.get("run_id"), "completed", {
            "total": s.total,
            "auto_approved": s.auto_approved,
            "human_approved": s.human_approved,
            "rejected": s.rejected,
        })


def _go_dashboard(prompt_demo: bool = True):
    """Enter the app workspace without starting the pipeline."""
    st.session_state.page = "app"
    st.session_state.workspace_view = "upload"
    if prompt_demo and not st.session_state.questions and not st.session_state.answers:
        st.session_state.demo_prompt = True


def _demo():
    """Start the interactive demo pipeline (only after user confirms)."""
    from samples.demo_data import DEMO_QUESTIONS
    st.session_state.update(
        questions=DEMO_QUESTIONS, answers=[], review_queue=[],
        demo=True, final_status="processing", pipe_stage=0,
        balloons_shown=False, total_review_items=0,
        auto_run=True, auto_run_start=time.time(), pipeline_done=False,
        workspace_view="upload", rsel=None, show_all_questions=False,
        just_finished_pipeline=False, demo_prompt=False,
        run_id=None, original_drafts={},
    )

def _load_demo_answers():
    from samples.demo_data import DEMO_ANSWERS, DEMO_REVIEW_QUEUE
    if not st.session_state.answers:
        st.session_state.update(
            answers=DEMO_ANSWERS, review_queue=list(DEMO_REVIEW_QUEUE),
            final_status="reviewing" if DEMO_REVIEW_QUEUE else "completed",
            total_review_items=len(DEMO_REVIEW_QUEUE),
            rsel=DEMO_REVIEW_QUEUE[0] if DEMO_REVIEW_QUEUE else None,
        )
        _remember_originals()
        # Demo runs participate in analytics + audit like real runs.
        if not st.session_state.get("run_id"):
            rid = db.create_run("Interactive demo questionnaire (27 pre-computed items)")
            st.session_state.run_id = rid
            for a in DEMO_ANSWERS:
                db.save_answer(
                    run_id=rid, question_id=a.question_id,
                    question_text=a.question_text, draft=a.draft,
                    evidence=a.evidence, confidence=a.confidence,
                    risk_flags=a.risk_flags, status=a.status,
                    decided_by="demo_seed",
                )
            db.add_event(run_id=rid, actor=_reviewer(), action="demo_loaded",
                         details={"items": len(DEMO_ANSWERS)})


def _start_guided_review():
    q = st.session_state.review_queue
    if q:
        st.session_state.rsel = q[0]
        st.session_state.workspace_view = "review"


def _fc(f):
    if "[CERT_WARNING]" in f or "[UNSUPPORTED_CLAIM]" in f:
        return "fp"
    if "[LEGAL_RISK]" in f:
        return "fd"
    if "[DATA_RESIDENCY]" in f:
        return "fw"
    return "fi"


def _fi(f):
    m = {"CERT_WARNING": "shield", "LEGAL_RISK": "scale", "DATA_RESIDENCY": "globe",
         "MISSING_EVIDENCE": "search", "LOW_CONFIDENCE": "chart", "ROUTING": "flag",
         "UNSUPPORTED_CLAIM": "alert"}
    for k, v in m.items():
        if k in f:
            return ic(v, 15)
    return ic("alert", 15)


def _dot(a):
    if a.status == "auto_approved":
        return "green"
    if a.status == "needs_review":
        return "yellow"
    if a.status == "human_approved":
        return "blue"
    if a.status == "rejected":
        return "red"
    return "yellow"


_init()

# ── QUERY PARAMS ──
# Open the dashboard and *ask* — never auto-start the demo pipeline.
qp = st.query_params
if st.session_state.page == "landing" and (qp.get("demo") == "1" or qp.get("app") == "1"):
    _go_dashboard(prompt_demo=True)
    # Clear param so refresh doesn't re-trigger (best-effort).
    with contextlib.suppress(Exception):
        del st.query_params["demo"]
    with contextlib.suppress(Exception):
        del st.query_params["app"]
    st.rerun()

# ── LANDING ──
if st.session_state.page == "landing":
    st.markdown(CSS_LANDING, unsafe_allow_html=True)

    st.markdown(f"""<div class="landing">
<nav class="lnav">
<a href="#" class="lnav-brand">{_logo(34, "nav")}Trust<span class="tl-accent">Loop</span></a>
<div class="lnav-links">
<a href="#how">How it works</a>
<a href="#features">Features</a>
<a href="#preview">Preview</a>
<a href="?app=1" class="lnav-cta">Open dashboard →</a>
</div>
</nav>

<div class="hero">
<div class="hero-inner">
<div class="hero-badge"><span class="hero-badge-dot"></span> AI-Powered Security Automation</div>
<h1 class="hero-title">Security questionnaires<br><span class="g1">automated</span>, <span class="g3">grounded</span>, <span class="g2">verified</span></h1>
<p class="hero-sub">Multi-agent AI parses questionnaires, retrieves grounded evidence from your knowledge base, runs compliance guardrails, and routes risky items to human reviewers — all in under 2 minutes.</p>
<div class="hero-btns">
<a href="?app=1" class="btn btn-fill">Open dashboard →</a>
<a href="#how" class="btn btn-ghost">See how it works</a>
</div>
<div class="hero-stats">
<div class="hero-stat"><div class="hero-stat-val v1">0%</div><div class="hero-stat-lbl">Hallucination Rate</div></div>
<div class="hero-stat"><div class="hero-stat-val v2">~55%</div><div class="hero-stat-lbl">Auto-Approved</div></div>
<div class="hero-stat"><div class="hero-stat-val v3">100%</div><div class="hero-stat-lbl">Routing Precision</div></div>
<div class="hero-stat"><div class="hero-stat-val v4">&lt;2m</div><div class="hero-stat-lbl">Full Pipeline</div></div>
</div>
</div>
<div class="hero-scroll">
<span>Scroll</span>
<div class="hero-scroll-arr"></div>
</div>
</div>
</div>

<div class="sec" id="how">
<div class="sec-tag">How It Works</div>
<div class="sec-title">Four agents. One pipeline.</div>
<div class="sec-desc">Each agent has a single responsibility. Typed state channels enforce data integrity. No black boxes.</div>
<div class="steps-wrapper">
<div class="steps-connector"></div>
<div class="steps">
<div class="step"><div class="step-n n1">01</div><h3>Parse & Classify</h3><p>Upload a questionnaire — questions are split, assigned UUIDs, and classified into 5 security categories.</p></div>
<div class="step"><div class="step-n n2">02</div><h3>Research & Ground</h3><p>Each question queries the approved knowledge base. Answers cite source documents — never made up.</p></div>
<div class="step"><div class="step-n n3">03</div><h3>Verify & Route</h3><p>7 compliance guardrails check certifications, legal risks, geographic concerns, evidence, confidence, and more.</p></div>
<div class="step"><div class="step-n n4">04</div><h3>Review & Deliver</h3><p>High-confidence items auto-approve. Risky items route to reviewers. Export to .xlsx, email, or Slack.</p></div>
</div>
</div>
</div>

<div class="sec" id="architecture">
<div class="sec-tag">Architecture</div>
<div class="sec-title">Multi-Agent System & Data Flow</div>
<div class="sec-desc">A detailed look at how questions move through our autonomous agent network to produce verified security answers.</div>

<div class="arch-flow">
<!-- Node 1: Intake -->
<div class="arch-node">
<div class="arch-badge">Agent 01</div>
<div class="arch-node-title">Intake Agent</div>
<div class="arch-node-desc">Splits, parses, and classifies input questions.</div>
<div class="arch-node-details">
<div><span>Input:</span> Raw text or Excel upload</div>
<div><span>Logic:</span> LLM-based category classifier</div>
<div><span>Output:</span> Categorized questions with UUIDs</div>
</div>
</div>

<div class="arch-arrow">
<svg viewBox="0 0 100 20" preserveAspectRatio="none">
<line x1="0" y1="10" x2="100" y2="10" stroke="rgba(99,102,241,0.12)" stroke-width="2" />
<line x1="0" y1="10" x2="100" y2="10" stroke="var(--primary-light)" stroke-width="2" stroke-dasharray="8 8" class="flow-line" />
</svg>
</div>

<!-- Node 2: Researcher -->
<div class="arch-node">
<div class="arch-badge">Agent 02</div>
<div class="arch-node-title">Researcher Agent</div>
<div class="arch-node-desc">Performs RAG to retrieve policy snippets and draft answers.</div>
<div class="arch-node-details">
<div><span>Input:</span> Categorized question</div>
<div><span>Logic:</span> Semantic search over policy KB</div>
<div><span>Output:</span> Grounded draft answers & citations</div>
</div>
</div>

<div class="arch-arrow">
<svg viewBox="0 0 100 20" preserveAspectRatio="none">
<line x1="0" y1="10" x2="100" y2="10" stroke="rgba(168,85,247,0.12)" stroke-width="2" />
<line x1="0" y1="10" x2="100" y2="10" stroke="var(--accent2)" stroke-width="2" stroke-dasharray="8 8" class="flow-line-accent" />
</svg>
</div>

<!-- Node 3: Verifier -->
<div class="arch-node">
<div class="arch-badge">Agent 03</div>
<div class="arch-node-title">Verifier Agent</div>
<div class="arch-node-desc">Evaluates compliance guardrails and computes confidence.</div>
<div class="arch-node-details">
<div><span>Input:</span> Draft answer + cited evidence</div>
<div><span>Logic:</span> Cert claims, residency, confidence checks</div>
<div><span>Output:</span> Risk flags & final confidence score</div>
</div>
</div>

<div class="arch-arrow">
<svg viewBox="0 0 100 20" preserveAspectRatio="none">
<line x1="0" y1="10" x2="100" y2="10" stroke="rgba(251,191,36,0.12)" stroke-width="2" />
<line x1="0" y1="10" x2="100" y2="10" stroke="var(--amber)" stroke-width="2" stroke-dasharray="8 8" class="flow-line-amber" />
</svg>
</div>

<!-- Node 4: Router -->
<div class="arch-node router-node">
<div class="arch-badge router-badge">Orchestrator</div>
<div class="arch-node-title">Router Node</div>
<div class="arch-node-desc">Evaluates risk flags and decides routing path.</div>
<div class="arch-node-details">
<div><span>Input:</span> Verified answer with flags</div>
<div><span>Rule:</span> Flags present OR confidence &lt; 70%</div>
<div><span>Routing:</span> Auto-Approve vs. Review Queue</div>
</div>
</div>
</div>

<!-- Path Split Section -->
<div class="arch-split">
<div class="split-path human-path">
<div class="path-label">
<span class="path-badge amber">Human Review Path</span>
<span class="path-desc">Has risk flags or confidence &lt; 70%</span>
</div>
<div class="split-connector-svg">
<svg viewBox="0 0 200 60" preserveAspectRatio="none" style="height: 60px; width: 100%;">
<path d="M 200 0 Q 150 40, 50 60" fill="none" stroke="rgba(251,191,36,0.15)" stroke-width="2"/>
<path d="M 200 0 Q 150 40, 50 60" fill="none" stroke="var(--amber)" stroke-width="2" stroke-dasharray="8 8" class="flow-line-amber"/>
</svg>
</div>
</div>

<div class="split-path auto-path">
<div class="path-label">
<span class="path-badge green">Auto-Approved Path</span>
<span class="path-desc">No risk flags, confidence &ge; 70%</span>
</div>
<div class="split-connector-svg">
<svg viewBox="0 0 200 60" preserveAspectRatio="none" style="height: 60px; width: 100%;">
<path d="M 0 0 Q 50 40, 150 60" fill="none" stroke="rgba(52,211,153,0.15)" stroke-width="2"/>
<path d="M 0 0 Q 50 40, 150 60" fill="none" stroke="var(--green)" stroke-width="2" stroke-dasharray="8 8" class="flow-line-green"/>
</svg>
</div>
</div>
</div>

<!-- Output Row -->
<div class="arch-outputs">
<!-- Reviewer Node -->
<div class="arch-node reviewer-node">
<div class="arch-badge">Human-in-the-Loop</div>
<div class="arch-node-title">Reviewer Action</div>
<div class="arch-node-desc">Interactive editing and approval UI.</div>
<div class="arch-node-details">
<div><span>Input:</span> Flagged answers & citations</div>
<div><span>Action:</span> Approve, Edit, or Reject</div>
<div><span>Output:</span> Finalized compliance response</div>
</div>
</div>

<!-- Spacer or short connector -->
<div class="arch-arrow small-arrow">
<svg viewBox="0 0 50 20" preserveAspectRatio="none">
<line x1="0" y1="10" x2="50" y2="10" stroke="rgba(255,255,255,0.1)" stroke-width="2"/>
<line x1="0" y1="10" x2="50" y2="10" stroke="var(--text3)" stroke-width="2" stroke-dasharray="6 6" class="flow-line-gray"/>
</svg>
</div>

<!-- Node 5: Deliver -->
<div class="arch-node delivery-node">
<div class="arch-badge delivery-badge">Delivery</div>
<div class="arch-node-title">Delivery Agent</div>
<div class="arch-node-desc">Publishes outputs and notifies integrations.</div>
<div class="arch-node-details">
<div><span>Action 1:</span> Export to formatted Excel (.xlsx)</div>
<div><span>Action 2:</span> Draft & send prospect email</div>
<div><span>Action 3:</span> Send Slack alert summary</div>
</div>
</div>
</div>
</div>

<div class="sec sec-wide" id="features" style="max-width:100%;padding-left:calc((100% - 1072px)/2);padding-right:calc((100% - 1072px)/2)">
<div class="sec-tag">Features</div>
<div class="sec-title">Built for security teams</div>
<div class="sec-desc">Everything you need to eliminate manual questionnaire work while maintaining compliance.</div>
<div class="feats">
<div class="feat"><div class="feat-ic i1">{ic("book", 22)}</div><h3>RAG Knowledge Base</h3><p>10 policy documents. Every answer grounded in source material — no hallucination risk.</p></div>
<div class="feat"><div class="feat-ic i2">{ic("shield-check", 22)}</div><h3>Compliance Guardrails</h3><p>Automated checks for certification claims, legal exposure, data residency, confidence thresholds, and more.</p></div>
<div class="feat"><div class="feat-ic i3">{ic("zap", 22)}</div><h3>Auto-Approval</h3><p>High-confidence answers with no risk flags auto-approve. ~55% never need human review.</p></div>
<div class="feat"><div class="feat-ic i4">{ic("user", 22)}</div><h3>Human-in-the-Loop</h3><p>Risky items route with confidence scores, risk flags, and evidence. Approve, edit, or reject in one click.</p></div>
<div class="feat"><div class="feat-ic i5">{ic("mail", 22)}</div><h3>Auto-Email</h3><p>Completed questionnaires emailed to prospects automatically when confidence exceeds threshold.</p></div>
<div class="feat"><div class="feat-ic i6">{ic("cpu", 22)}</div><h3>REST API</h3><p>Programmatic access via FastAPI. Export to .xlsx, Slack notifications, integrate with your tools.</p></div>
</div>
</div>

<div class="sec" id="preview">
<div class="sec-tag">See It In Action</div>
<div class="sec-title">The review panel</div>
<div class="sec-desc">Split-panel review interface for security questionnaires — the core of the TrustLoop demo.</div>
<div class="mockup-wrap">
<div class="mockup-bar">
<div class="mockup-dot md1"></div>
<div class="mockup-dot md2"></div>
<div class="mockup-dot md3"></div>
<div class="mockup-tab">
<div class="mockup-tab-item">Upload</div>
<div class="mockup-tab-item active">Review</div>
<div class="mockup-tab-item">Deliver</div>
<div class="mockup-tab-item">KB</div>
</div>
</div>
<div class="mockup-body">
<div class="mockup-left">
<div style="font-size:10px;font-weight:600;color:#5a6478;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;padding:0 4px">Questions (27) · 8 to review</div>
<div class="mockup-left-item active"><div class="mockup-left-dot yellow"></div><span>Are you HIPAA certified?</span></div>
<div class="mockup-left-item"><div class="mockup-left-dot yellow"></div><span>Are you PCI DSS certified?</span></div>
<div class="mockup-left-item"><div class="mockup-left-dot yellow"></div><span>Are you FedRAMP authorized?</span></div>
<div class="mockup-left-item"><div class="mockup-left-dot yellow"></div><span>Where is customer data stored?</span></div>
<div class="mockup-left-item"><div class="mockup-left-dot green"></div><span>Do you encrypt data at rest?</span></div>
<div class="mockup-left-item"><div class="mockup-left-dot green"></div><span>What is your MFA policy?</span></div>
</div>
<div class="mockup-right">
<div class="mockup-right-q">Are you HIPAA certified?</div>
<div class="mockup-right-conf">
<div class="mockup-right-gauge">93%</div>
<div style="flex:1"><div style="font-size:10px;font-weight:600;color:#5a6478;text-transform:uppercase;letter-spacing:.05em">Confidence</div>
<div class="mockup-right-bar"><div class="mockup-right-fill"></div></div></div>
</div>
<div class="mockup-right-flag">{ic("alert", 12)} Acme SaaS does not hold HIPAA certification.</div>
<div class="mockup-right-edit">No. Acme SaaS is NOT HIPAA certified and does NOT sign Business Associate Agreements (BAAs). Customers must not store Protected Health Information (PHI) on the platform.</div>
<div class="mockup-right-acts">
<div class="mockup-right-btn green">Approve</div>
<div class="mockup-right-btn">Edit</div>
<div class="mockup-right-btn red">Reject</div>
</div>
</div>
</div>
</div>
</div>

<div class="cta">
<div class="sec-tag" style="margin-bottom:20px">Live demo</div>
<h2>Ready to automate security questionnaires?</h2>
<p>Try the interactive demo — 27 questions across 5 security categories. No sign-up required.</p>
<a href="?app=1" class="btn btn-fill">Open dashboard →</a>
</div>
<div class="foot">
<div style="display:flex;align-items:center;gap:10px">{_logo(22, "foot")}<span style="font-weight:700;color:var(--text2)">Trust<span class="tl-accent">Loop</span></span><span>© 2026</span></div>
<div style="display:flex;gap:12px;align-items:center;color:var(--text3);font-weight:500">
<span>LangGraph</span><span style="opacity:.4">·</span><span>RAG</span><span style="opacity:.4">·</span><span>Streamlit</span><span style="opacity:.4">·</span><span>FastAPI</span>
</div>
</div>
""", unsafe_allow_html=True)

    with st.sidebar:
        st.markdown(_brand_row("Try the live demo", 36, "landside"), unsafe_allow_html=True)
        st.markdown('<div class="side-sec">Get started</div>', unsafe_allow_html=True)
        st.caption("Open the dashboard first — you'll be asked before the interactive demo starts.")
        if st.button("Open dashboard", use_container_width=True, type="primary"):
            _go_dashboard(prompt_demo=True)
            st.rerun()
        st.markdown('<div class="side-sec">Mode</div>', unsafe_allow_html=True)
        if USE_LLM:
            st.success(f"LLM: {LLM_PROVIDER.upper()}")
        else:
            st.info("Offline mode (RAG only)")


# ── APP ──
else:
    st.markdown(CSS_APP, unsafe_allow_html=True)

    st.markdown("""
    <div class="app-bg"></div>
    """, unsafe_allow_html=True)

    # Sidebar — rendered first so it's always visible
    with st.sidebar:
        st.markdown(_brand_row("Security questionnaire AI", 38, "appside"), unsafe_allow_html=True)
        if st.button("Back to home", use_container_width=True):
            st.session_state.page = "landing"
            st.rerun()
        st.markdown('<div class="side-sec">Quick start</div>', unsafe_allow_html=True)
        if st.button("Start interactive demo", use_container_width=True, type="primary"):
            _demo()
            st.rerun()
        st.markdown('<div class="side-sec">Reviewer identity</div>', unsafe_allow_html=True)
        st.text_input(
            "Your name (recorded in the audit trail)",
            key="reviewer_name",
            placeholder="e.g. jane.doe@acme.com",
            label_visibility="collapsed",
        )
        if st.session_state.answers:
            s = summarize_run(st.session_state.answers)
            st.markdown('<div class="side-sec">Run summary</div>', unsafe_allow_html=True)
            auto_rate = int(s.auto_pct) if s.total else 0
            st.markdown(f"""<div class="side-summary">
              <div class="side-summary-row"><span>Total</span><span>{s.total}</span></div>
              <div class="side-summary-row"><span>Auto-approved</span><span style="color:var(--green)">{s.auto_approved}</span></div>
              <div class="side-summary-row"><span>Needs review</span><span style="color:var(--amber)">{s.needs_review}</span></div>
              <div class="side-summary-row"><span>Human-approved</span><span style="color:var(--blue)">{s.human_approved}</span></div>
              <div class="side-summary-row"><span>Rejected</span><span style="color:var(--red)">{s.rejected}</span></div>
              <div class="side-summary-row"><span>Auto rate</span><span style="color:var(--primary-light)">{auto_rate}%</span></div>
            </div>""", unsafe_allow_html=True)
        st.markdown('<div class="side-sec">Mode</div>', unsafe_allow_html=True)
        if USE_LLM:
            st.success(f"LLM: {LLM_PROVIDER.upper()}")
        else:
            st.info("Offline · RAG only")

    # App bar
    running = bool(st.session_state.get("auto_run"))
    n_q = len(st.session_state.questions)
    n_rev = len(st.session_state.review_queue)
    mode_lbl = "Pipeline running…" if running else ("Demo mode" if st.session_state.demo else "Live mode")
    mode_cls = "appbar-badge running" if running else "appbar-badge"
    st.markdown(f"""
    <div class="appbar">
      <a href="#" class="appbar-brand">
        {_logo(30, "appbar")}
        <span class="appbar-brand-name">
          <b>Trust<span class="tl-accent">Loop</span></b>
          <span>Command center</span>
        </span>
      </a>
      <div class="appbar-actions">
        <span class="appbar-meta">{ic("clipboard", 13)} {n_q} questions</span>
        <span class="appbar-meta">{ic("clock", 13)} {n_rev} in review</span>
        <span class="{mode_cls}">{ic("clock" if running else "zap", 13)} {mode_lbl}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Command-center header
    if st.session_state.answers:
        s = summarize_run(st.session_state.answers)
        done = s.auto_approved + s.human_approved + s.rejected
        progress = int(done / s.total * 100) if s.total else 0
        auto_rate = int(s.auto_pct) if s.total else 0
        status_pill = (
            f'<span class="dash-pill warn">{ic("clock", 13)} Review queue open</span>'
            if s.needs_review
            else f'<span class="dash-pill on">{ic("check-circle", 13)} Ready to deliver</span>'
        )
        if st.session_state.get("pipeline_done") or st.session_state.demo:
            status_pill += f'<span class="dash-pill">{ic("play", 13)} Demo loaded</span>'
        st.markdown(f"""
        <div class="dash-head">
          <div class="dash-head-row">
            <div>
              <div class="dash-head-title">Questionnaire workspace</div>
              <div class="dash-head-sub">Grounded answers, compliance routing, and human review — track progress and ship artifacts from one place.</div>
            </div>
            <div class="dash-head-pills">
              <span class="dash-pill"><strong>{auto_rate}%</strong> auto-approved</span>
              {status_pill}
            </div>
          </div>
          <div class="dash-progress">
            <div class="dash-progress-top">
              <span class="dash-progress-lbl">Resolution progress</span>
              <span class="dash-progress-val">{done}/{s.total} resolved · {progress}%</span>
            </div>
            <div class="dash-progress-bar"><div class="dash-progress-fill" style="width:{progress}%"></div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Pipeline — card shell with stage info
    ps = st.session_state.pipe_stage
    nodes = [(ic("clipboard", 20), "Upload"), (ic("search", 20), "Parse"), (ic("cpu", 20), "Research"),
             (ic("shield-check", 20), "Verify"), (ic("check-circle", 20), "Deliver")]
    open_reviews = sum(1 for a in st.session_state.answers if a.status == "needs_review")
    stage_descs = [
        "Upload your security questionnaire (.xlsx or .txt)",
        "Splitting questions and classifying into 5 security categories",
        "Querying knowledge base with RAG for grounded answers",
        "Running 7 compliance guardrails on each answer",
        (
            f"{open_reviews} item(s) flagged — review to finish delivery"
            if open_reviews
            else "All items resolved — ready for delivery"
        ),
    ]
    stage_icons = [ic("clipboard", 14), ic("zap", 14), ic("search", 14), ic("shield-check", 14),
                   ic("eye", 14) if open_reviews and ps >= 4 else ic("play", 14)]
    stage_info = stage_descs[ps] if 0 <= ps < len(stage_descs) else "Start by loading a demo or uploading a questionnaire"
    stage_icon = stage_icons[ps] if 0 <= ps < len(stage_icons) else ic("zap", 14)
    stage_n = min(max(ps, 0), 4) + 1
    h = f'''<div class="pipe-shell">
      <div class="pipe-shell-title"><h3>Agent pipeline</h3><span>Stage {stage_n} of 5</span></div>
      <div class="pipe-strip">'''
    for i, (node_ic, lbl) in enumerate(nodes):
        cls = "done" if ps > i else ("active" if ps == i else "")
        if i > 0:
            seg = "done" if ps > i else ("active" if ps == i else "")
            h += f'<div class="pipe-seg {seg}"></div>'
        h += f'<div class="pipe-node {cls}"><div class="pipe-ic">{node_ic}</div><div class="pipe-lbl">{lbl}</div></div>'
    h += f'</div><div class="pipe-stage-info">{stage_icon} <strong>{stage_info}</strong></div></div>'
    st.markdown(h, unsafe_allow_html=True)

    # Dashboard KPI bar
    if st.session_state.answers:
        s = summarize_run(st.session_state.answers)
        chips_html = f"""
          <div class="chip ct"><div class="chip-ic">{ic("file", 18)}</div><span><div class="chip-val">{s.total}</div>Total questions</span></div>
          <div class="chip co"><div class="chip-ic">{ic("check-circle", 18)}</div><span><div class="chip-val">{s.auto_approved}</div>Auto-approved</span></div>
          <div class="chip cw"><div class="chip-ic">{ic("clock", 18)}</div><span><div class="chip-val">{s.needs_review}</div>Needs review</span></div>
          <div class="chip ci"><div class="chip-ic">{ic("user", 18)}</div><span><div class="chip-val">{s.human_approved}</div>Human-approved</span></div>
          <div class="chip cr"><div class="chip-ic">{ic("x-circle", 18)}</div><span><div class="chip-val">{s.rejected}</div>Rejected</span></div>
        """
        st.markdown(f'<div class="dash-bar">{chips_html}</div>', unsafe_allow_html=True)

    # Auto-run pipeline for demo — advances one stage per re-run with timing
    if st.session_state.get("auto_run"):
        elapsed = time.time() - st.session_state.auto_run_start
        new_stage = min(int(elapsed / 2.5), 4)
        if new_stage > st.session_state.pipe_stage:
            st.session_state.pipe_stage = new_stage
            if new_stage >= 3:
                _load_demo_answers()
            if new_stage >= 4:
                st.session_state.auto_run = False
                st.session_state.pipeline_done = True
                st.session_state.final_status = "reviewing"
                st.session_state.just_finished_pipeline = True
                if st.session_state.review_queue:
                    st.session_state.rsel = st.session_state.review_queue[0]
                    st.session_state.workspace_view = "review"

    # Workspace nav (programmatic — supports auto-jump to guided review)
    n_review = len(st.session_state.review_queue)
    view = st.session_state.workspace_view
    nav_items = [
        ("upload", "Summary", None),
        ("review", "Review", n_review or None),
        ("deliver", "Deliver", None),
        ("analytics", "Analytics", None),
        ("audit", "Audit", None),
        ("kb", "Knowledge Base", None),
    ]
    nc = st.columns(6)
    for i, (key, label, badge) in enumerate(nav_items):
        with nc[i]:
            btn_label = f"{label}" + (f" ({badge})" if badge else "")
            if st.button(
                btn_label,
                use_container_width=True,
                type="primary" if view == key else "secondary",
                key=f"ws_nav_{key}",
            ):
                st.session_state.workspace_view = key
                if (
                    key == "review"
                    and st.session_state.review_queue
                    and st.session_state.rsel not in st.session_state.review_queue
                ):
                    st.session_state.rsel = st.session_state.review_queue[0]
                st.rerun()

    # ── UPLOAD / SUMMARY ──
    if view == "upload":
        empty_workspace = (
            not st.session_state.questions
            and not st.session_state.answers
            and not st.session_state.get("auto_run")
        )
        if empty_workspace:
            # Ask first — nothing runs until the user confirms
            st.markdown(f"""
            <div class="summary-hero">
              <div class="summary-hero-ic">{ic("play", 36)}</div>
              <div class="summary-hero-t">Start the interactive demo?</div>
              <div class="summary-hero-s">
                We'll run a 27-question security questionnaire through the multi-agent pipeline,
                then walk you through flagged items one at a time. Nothing starts until you confirm.
              </div>
              <div class="summary-stats">
                <div class="summary-stat"><div class="summary-stat-v" style="color:var(--primary-light)">27</div><div class="summary-stat-l">Sample questions</div></div>
                <div class="summary-stat"><div class="summary-stat-v" style="color:var(--green)">~55%</div><div class="summary-stat-l">Auto-approved</div></div>
                <div class="summary-stat"><div class="summary-stat-v" style="color:var(--amber)">~8</div><div class="summary-stat-l">Guided reviews</div></div>
              </div>
            </div>
            """, unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 2, 1])
            with c2:
                if st.button("Start interactive demo", use_container_width=True, type="primary", key="confirm_demo"):
                    _demo()
                    st.rerun()
                st.caption("You can also start the demo from the sidebar.")
        elif st.session_state.get("auto_run") and not st.session_state.answers:
            # Pipeline animating after user confirmed demo
            qs = st.session_state.questions
            elapsed = time.time() - st.session_state.auto_run_start
            stage = st.session_state.pipe_stage
            if stage == 0:
                st.markdown(f"""<div class="loading"><div class="loading-ic">{ic("clock", 40)}</div>
                  <div class="loading-t">Uploading questionnaire...</div>
                  <div class="loading-sub">Processing sample questionnaire…</div></div>""", unsafe_allow_html=True)
            elif stage == 1:
                st.markdown(f"""<div class="loading"><div class="loading-ic">{ic("cpu", 40)}</div>
                  <div class="loading-t">Parsing & classifying questions...</div>
                  <div class="loading-sub">Splitting into categories.</div></div>""", unsafe_allow_html=True)
            elif stage == 2:
                pct = min(int((elapsed - 5.0) / 2.5 * 100), 100)
                num_answered = int(len(qs) * (pct / 100)) if qs else 0
                st.markdown(f"""<div class="loading"><div class="loading-ic">{ic("cpu", 40)}</div>
                  <div class="loading-t">Researching grounded answers ({num_answered}/{len(qs) or 27})</div>
                  <div class="loading-sub">RAG retrieval over the knowledge base.</div></div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""<div class="loading"><div class="loading-ic">{ic("shield-check", 40)}</div>
                  <div class="loading-t">Running compliance guardrails...</div>
                  <div class="loading-sub">Routing risky items into guided review.</div></div>""", unsafe_allow_html=True)
                _load_demo_answers()
        else:
            qs = st.session_state.questions
            has_answers = bool(st.session_state.answers)

            if st.session_state.get("auto_run"):
                elapsed = time.time() - st.session_state.auto_run_start
                stage = st.session_state.pipe_stage
                if stage == 0:
                    st.markdown(f"""<div class="loading"><div class="loading-ic">{ic("clock", 40)}</div>
                      <div class="loading-t">Uploading questionnaire...</div>
                      <div class="loading-sub">Processing incoming file "questionnaire_enterprise.xlsx" (24 KB)...</div></div>""", unsafe_allow_html=True)
                elif stage == 1:
                    st.markdown(f"""<div class="loading"><div class="loading-ic">{ic("cpu", 40)}</div>
                      <div class="loading-t">Parsing & classifying questions...</div>
                      <div class="loading-sub">Splitting into categories — no need to read every row yet.</div></div>""", unsafe_allow_html=True)
                elif stage == 2:
                    pct = min(int((elapsed - 5.0) / 2.5 * 100), 100)
                    num_answered = int(len(qs) * (pct / 100))
                    st.markdown(f"""<div class="loading"><div class="loading-ic">{ic("cpu", 40)}</div>
                      <div class="loading-t">Researching grounded answers ({num_answered}/{len(qs)})</div>
                      <div class="loading-sub">RAG retrieval over the knowledge base — showing live activity only.</div></div>""", unsafe_allow_html=True)
                    # Show only a short sliding window, not all 27 rows
                    start = max(0, num_answered - 2)
                    end = min(len(qs), num_answered + 3)
                    rows = ""
                    for idx in range(start, end):
                        q = qs[idx]
                        if idx < num_answered:
                            status_text, status_cls = "Grounded", "auto"
                        elif idx == num_answered:
                            status_text, status_cls = "Researching…", "review"
                        else:
                            status_text, status_cls = "Pending", "general"
                        rows += f'<div class="qrow"><div class="qrow-n">{idx + 1}</div><div class="qrow-t">{q.text}</div><div class="qrow-status {status_cls}">{status_text}</div></div>'
                    st.markdown(f'<div class="qlist" style="max-width:720px;margin:0 auto">{rows}</div>', unsafe_allow_html=True)
                elif stage == 3:
                    st.markdown(f"""<div class="loading"><div class="loading-ic">{ic("shield-check", 40)}</div>
                      <div class="loading-t">Running compliance guardrails...</div>
                      <div class="loading-sub">Routing risky items into the guided review queue.</div></div>""", unsafe_allow_html=True)
                    _load_demo_answers()
            else:
                cats = {}
                for q in qs:
                    cats[q.category] = cats.get(q.category, 0) + 1

                if has_answers:
                    s = summarize_run(st.session_state.answers)
                    n_rev = len(st.session_state.review_queue)
                    # Clean summary — no wall of questions
                    st.markdown(f"""
                    <div class="summary-hero">
                      <div class="summary-hero-ic">{ic("eye" if n_rev else "check-circle", 36)}</div>
                      <div class="summary-hero-t">{"Ready for guided review" if n_rev else "All clear — ready to deliver"}</div>
                      <div class="summary-hero-s">
                        {"High-confidence answers were auto-approved. We'll walk you through the remaining flagged items one at a time." if n_rev else "Nothing left in the review queue. Export the workbook or send artifacts from Deliver."}
                      </div>
                      <div class="summary-stats">
                        <div class="summary-stat"><div class="summary-stat-v" style="color:var(--text)">{s.total}</div><div class="summary-stat-l">Total questions</div></div>
                        <div class="summary-stat"><div class="summary-stat-v" style="color:var(--green)">{s.auto_approved}</div><div class="summary-stat-l">Auto-approved</div></div>
                        <div class="summary-stat"><div class="summary-stat-v" style="color:var(--amber)">{n_rev}</div><div class="summary-stat-l">Need your review</div></div>
                      </div>
                      <div class="cat-pills">
                        {"".join(f'<span class="cat-pill">{c.replace("-", " ")} · {n}</span>' for c, n in sorted(cats.items()))}
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

                    if n_rev:
                        # Preview only first 3 flagged items
                        preview = ""
                        for qid in st.session_state.review_queue[:3]:
                            a = _ans(qid)
                            if not a:
                                continue
                            flag = a.risk_flags[0] if a.risk_flags else "needs review"
                            preview += f'<div class="flagged-row"><div class="fr-n">{qid}</div><div class="fr-t">{a.question_text}</div><div class="fr-flag">{flag}</div></div>'
                        more = n_rev - 3
                        st.markdown(f"""
                        <div class="flagged-preview">
                          <div class="flagged-preview-h">Up next in guided review{f" · +{more} more" if more > 0 else ""}</div>
                          {preview}
                        </div>
                        """, unsafe_allow_html=True)

                        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                        cta1, cta2, cta3 = st.columns([1, 2, 1])
                        with cta2:
                            if st.button("Start guided review", use_container_width=True, type="primary", key="start_guided"):
                                _start_guided_review()
                                st.rerun()
                            st.caption("We'll show one flagged question at a time. Approve or reject to advance automatically.")
                    else:
                        cta1, cta2, cta3 = st.columns([1, 2, 1])
                        with cta2:
                            if st.button("Go to deliverables", use_container_width=True, type="primary", key="go_deliver"):
                                st.session_state.workspace_view = "deliver"
                                st.rerun()

                    with st.expander("Browse all questions (optional)", expanded=False):
                        search_q = st.text_input("Filter", placeholder="Filter questions…", label_visibility="collapsed", key="q_filter")
                        filtered = qs
                        if search_q:
                            filtered = [q for q in qs if search_q.lower() in q.text.lower()]
                        rows = ""
                        for i, q in enumerate(filtered):
                            status_text, status_cls = "", ""
                            a = _ans(q.id)
                            if a:
                                if a.status == "auto_approved":
                                    status_text, status_cls = "Auto", "auto"
                                elif a.status == "needs_review":
                                    status_text, status_cls = "Review", "review"
                                elif a.status == "human_approved":
                                    status_text, status_cls = "Done", "auto"
                                elif a.status == "rejected":
                                    status_text, status_cls = "Rejected", "review"
                            rows += f'<div class="qrow"><div class="qrow-n">{i + 1}</div><div class="qrow-t">{q.text}</div><div class="qrow-c {q.category}">{q.category.replace("-", " ")}</div>{"<div class=\"qrow-status " + status_cls + "\">" + status_text + "</div>" if status_text else ""}</div>'
                        st.markdown(f'<div class="qlist">{rows}</div>', unsafe_allow_html=True)
                else:
                    # Parsed but not run yet — compact list + run CTA
                    st.markdown(f"""<div class="summary-hero">
                      <div class="summary-hero-ic">{ic("clipboard", 36)}</div>
                      <div class="summary-hero-t">{len(qs)} questions parsed</div>
                      <div class="summary-hero-s">Run the multi-agent pipeline to ground answers and route risky items to guided review.</div>
                      <div class="cat-pills">{"".join(f'<span class="cat-pill">{c.replace("-", " ")} · {n}</span>' for c, n in sorted(cats.items()))}</div>
                    </div>""", unsafe_allow_html=True)
                    c1, c2, c3 = st.columns([1, 2, 1])
                    with c2:
                        if st.button("Run multi-agent pipeline", use_container_width=True, type="primary"):
                            st.session_state.pipe_stage = 1
                            st.session_state.demo = False
                            st.rerun()
                    with st.expander("Preview questions", expanded=False):
                        rows = "".join(
                            f'<div class="qrow"><div class="qrow-n">{i + 1}</div><div class="qrow-t">{q.text}</div><div class="qrow-c {q.category}">{q.category.replace("-", " ")}</div></div>'
                            for i, q in enumerate(qs)
                        )
                        st.markdown(f'<div class="qlist">{rows}</div>', unsafe_allow_html=True)

            if st.session_state.pipe_stage == 1 and not st.session_state.demo:
                ph = st.empty()
                ph.markdown(f"""<div class="loading"><div class="loading-ic">{ic("zap", 40)}</div>
                  <div class="loading-t">Running multi-agent pipeline...</div>
                  <div class="loading-sub">Intake → Research → Compliance → Routing</div></div>""", unsafe_allow_html=True)
                raw = "\n".join(q.text for q in st.session_state.questions)
                state = run_pipeline(raw)
                st.session_state.questions = list(state["questions"])
                st.session_state.answers = list(state["answers"])
                st.session_state.review_queue = list(state["review_queue"])
                st.session_state.final_status = state["final_status"]
                st.session_state.run_id = state.get("run_id")
                _remember_originals()
                st.session_state.run_complete = state["final_status"] == "completed"
                st.session_state.pipe_stage = 4 if not state["review_queue"] else 3
                st.session_state.step = 3 if not state["review_queue"] else 2
                st.session_state.total_review_items = len(state["review_queue"])
                if state["review_queue"]:
                    st.session_state.rsel = state["review_queue"][0]
                    st.session_state.workspace_view = "review"
                else:
                    st.session_state.workspace_view = "deliver"
                ph.empty()
                st.rerun()

    # ── GUIDED REVIEW (one item at a time) ──
    elif view == "review":
        ans = st.session_state.answers
        if not ans:
            st.markdown(f"""<div class="empty"><div class="empty-ic">{ic("eye", 44)}</div><div class="empty-t">No answers yet</div><div class="empty-sub">Load the demo or run the pipeline first — then we'll guide you through flagged items.</div></div>""", unsafe_allow_html=True)
        elif not st.session_state.review_queue:
            st.markdown(f"""<div class="autoemail"><div class="autoemail-ic">{ic("check-circle", 18)}</div><div><div class="autoemail-t">All items resolved!</div><div class="autoemail-sub">Nothing left to review. Continue to Deliver for export, email, and Slack.</div></div></div>""", unsafe_allow_html=True)
            if not st.session_state.balloons_shown:
                st.balloons()
                st.session_state.balloons_shown = True
            c1, c2, c3 = st.columns([1, 2, 1])
            with c2:
                if st.button("Continue to deliverables", use_container_width=True, type="primary", key="rev_to_del"):
                    st.session_state.workspace_view = "deliver"
                    st.rerun()
        else:
            qids = list(st.session_state.review_queue)
            # Always focus current / first item — no manual picker
            sel = st.session_state.get("rsel")
            if sel not in qids:
                sel = qids[0]
                st.session_state.rsel = sel

            remaining = len(qids)
            total = st.session_state.total_review_items or remaining
            total = max(total, remaining)
            done = max(0, total - remaining)
            pct = int(done / total * 100) if total > 0 else 0
            # Position among original queue when possible
            pos = done + 1

            # Step dots
            steps_html = ""
            for i in range(total):
                cls = "done" if i < done else ("active" if i == done else "")
                steps_html += f'<div class="guide-step {cls}"></div>'

            st.markdown(f"""
            <div class="guide-bar">
              <div class="guide-bar-top">
                <div class="guide-bar-title">Guided review</div>
                <div class="guide-bar-meta">Item {pos} of {total} · {remaining} left</div>
              </div>
              <div class="review-progress-bar" style="height:7px;background:rgba(255,255,255,.05);border-radius:999px;overflow:hidden">
                <div class="review-progress-fill" style="width:{pct}%;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--green),var(--primary-light));box-shadow:0 0 10px rgba(52,211,153,.25)"></div>
              </div>
              <div class="guide-steps">{steps_html}</div>
            </div>
            <div class="guide-hint">Decide on this item — <strong>Approve</strong>, <strong>Edit & approve</strong>, or <strong>Reject</strong> — and the next one opens automatically.</div>
            """, unsafe_allow_html=True)

            cur = _ans(sel)
            if cur:
                cat = next((q.category for q in st.session_state.questions if q.id == cur.question_id), "general")
                cat_icons = {"technical": "cpu", "certification": "shield-check", "legal": "scale", "data-privacy": "globe", "general": "file"}
                cat_icon = ic(cat_icons.get(cat, "file"), 13)
                conf_pct = int(cur.confidence * 100)
                clr = "#34d399" if cur.confidence >= 0.7 else ("#fbbf24" if cur.confidence >= 0.4 else "#ef4444")
                grd = "linear-gradient(90deg,#059669,#34d399)" if cur.confidence >= 0.7 else (
                    "linear-gradient(90deg,#d97706,#fbbf24)" if cur.confidence >= 0.4 else "linear-gradient(90deg,#dc2626,#ef4444)")

                st.markdown('<div class="review-focus">', unsafe_allow_html=True)
                st.markdown(f"""
                <div class="rpanel">
                  <div class="rpanel-head">
                    <span class="rpanel-id">{cur.question_id}</span>
                    <span class="rpanel-cat qrow-c {cat}">{cat_icon} {cat.replace("-", " ")}</span>
                  </div>
                  <div class="rpanel-q">{cur.question_text}</div>
                </div>
                <div class="conf-grid" style="margin-top:14px">
                  <div class="conf-card" style="background:rgba(99,102,241,.03);border:1px solid rgba(99,102,241,.08)">
                    <div class="conf-card-top">
                      <span class="conf-card-lbl">Confidence</span>
                      <span class="conf-card-val" style="color:{clr}">{conf_pct}%</span>
                    </div>
                    <div class="conf-card-bar"><div class="conf-card-fill" style="width:{conf_pct}%;background:{grd}"></div></div>
                    <div style="font-size:10px;color:var(--text3);margin-top:6px;font-weight:600">
                      {('Above threshold (70%)' if cur.confidence >= 0.7 else 'Below threshold (70%)')}
                    </div>
                  </div>
                  <div class="conf-card" style="background:rgba(251,191,36,.03);border:1px solid rgba(251,191,36,.1)">
                    <div class="conf-card-top">
                      <span class="conf-card-lbl">Why it's here</span>
                      <span class="conf-card-val" style="font-size:14px;color:var(--amber)">Needs review</span>
                    </div>
                    <div style="font-size:11px;color:var(--text2);margin-top:6px;font-weight:600">
                      {len(cur.evidence)} source(s) · {len(cur.risk_flags)} risk flag(s)
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

                if cur.risk_flags:
                    fh = "".join(
                        f'<div class="flag {_fc(f)}"><span class="flag-icon">{_fi(f)}</span> {f}</div>'
                        for f in cur.risk_flags
                    )
                    st.markdown(f'<div style="margin-top:14px"><div class="answer-section-lbl">Risk flags</div><div class="flags">{fh}</div></div>', unsafe_allow_html=True)

                if cur.evidence:
                    ch = "".join(f'<span class="cite">{ic("file", 12)} {e}</span>' for e in cur.evidence)
                    st.markdown(f'<div style="margin-top:8px"><div class="answer-section-lbl">Evidence</div><div class="cites">{ch}</div></div>', unsafe_allow_html=True)

                st.markdown('<div class="answer-section" style="margin-top:16px"><div class="answer-section-lbl">Draft answer</div></div>', unsafe_allow_html=True)
                ed = st.text_area("Answer", value=cur.draft, height=140, label_visibility="collapsed",
                                  key=f"d_{cur.question_id}")

                # Live diff: original pipeline draft vs current editor content
                orig = st.session_state.original_drafts.get(cur.question_id, cur.draft)
                if ed.strip() != orig.strip():
                    st.markdown(f"""
                    <div class="diffbox">
                      <div class="diffbox-h">Edited — changes vs original draft</div>
                      <div class="diff-cols">
                        <div class="diff-col diff-del"><div class="diff-lbl">Original</div><div class="diff-body">{orig}</div></div>
                        <div class="diff-col diff-add"><div class="diff-lbl">Current edit</div><div class="diff-body">{ed}</div></div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown('<div class="btn-approve">', unsafe_allow_html=True)
                    if st.button("Approve & next", use_container_width=True, key=f"ap_{cur.question_id}", type="primary"):
                        _upd(cur.model_copy(update={"draft": ed, "status": "human_approved"}))
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                with c2:
                    st.markdown('<div class="btn-edit">', unsafe_allow_html=True)
                    if st.button("Edit & approve", use_container_width=True, key=f"ed_{cur.question_id}"):
                        _upd(cur.model_copy(update={"draft": ed, "status": "human_approved"}))
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                with c3:
                    st.markdown('<div class="btn-reject">', unsafe_allow_html=True)
                    if st.button("Reject & next", use_container_width=True, key=f"rj_{cur.question_id}"):
                        _upd(cur.model_copy(update={"draft": ed, "status": "rejected"}))
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('</div>', unsafe_allow_html=True)

                with st.expander("More options", expanded=False):
                    if st.button("Approve all remaining (skip guided flow)", use_container_width=True, key="approve_all"):
                        actor = _reviewer()
                        for a in st.session_state.answers:
                            if a.question_id in st.session_state.review_queue and a.status == "needs_review":
                                a.status = "human_approved"
                                db.record_decision(
                                    run_id=st.session_state.get("run_id"),
                                    question_id=a.question_id,
                                    actor=actor,
                                    action="review_bulk_approve",
                                    final_text=a.draft,
                                    new_status="human_approved",
                                )
                        st.session_state.review_queue = []
                        st.session_state.final_status = "completed"
                        st.session_state.pipe_stage = 4
                        st.session_state.workspace_view = "deliver"
                        s_all = summarize_run(st.session_state.answers)
                        db.complete_run(st.session_state.get("run_id"), "completed", {
                            "total": s_all.total,
                            "auto_approved": s_all.auto_approved,
                            "human_approved": s_all.human_approved,
                            "rejected": s_all.rejected,
                        })
                        st.rerun()
                    st.caption("Use only if you trust the drafts for every remaining flagged item.")

    # ── DELIVER ──
    elif view == "deliver":
        st.markdown("""<div class="tab-head"><div class="tab-head-t">Delivery & artifacts</div>
          <div class="tab-head-s">Export the finished workbook, preview the prospect email, and share a Slack-ready summary.</div></div>""", unsafe_allow_html=True)
        ans = st.session_state.answers
        if not ans:
            st.markdown(f"""<div class="empty"><div class="empty-ic">{ic("package", 44)}</div><div class="empty-t">No deliverables yet</div><div class="empty-sub">Complete the pipeline and clear the review queue first.</div></div>""", unsafe_allow_html=True)
        elif st.session_state.review_queue:
            n = len(st.session_state.review_queue)
            st.markdown(f"""<div class="info-banner" style="border-color:rgba(251,191,36,.22);background:linear-gradient(135deg,rgba(251,191,36,.08),rgba(255,255,255,.02))">
              <div class="info-banner-ic" style="background:rgba(251,191,36,.12);color:#FBBF24">{ic("clock", 18)}</div>
              <div class="info-banner-content">
                <div class="info-banner-title" style="color:var(--amber)">{n} item(s) still need review</div>
                <div class="info-banner-sub">Finish guided review first — each decision advances automatically.</div>
              </div>
            </div>""", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 2, 1])
            with c2:
                if st.button("Resume guided review", use_container_width=True, type="primary", key="resume_guided"):
                    _start_guided_review()
                    st.rerun()
        else:
            s = summarize_run(ans)
            er = send_prospect_email(ans, dry_run=True)
            if er.get("email"):
                st.session_state.email_sent = True
                avg = er.get("avg_confidence", 0)
                st.markdown(f"""<div class="autoemail"><div class="autoemail-ic">{ic("mail", 18)}</div>
                  <div><div class="autoemail-t">Auto-email ready — {avg:.0%} average confidence</div>
                  <div class="autoemail-sub">The completed questionnaire is ready to send to the prospect.</div></div></div>""", unsafe_allow_html=True)

            # Stats dashboard
            st.markdown(f"""<div class="dgrid">
              <div class="dstat"><div class="dstat-icon">{ic("file", 22)}</div><div class="dstat-k">Total Questions</div><div class="dstat-v" style="color:var(--text)">{s.total}</div></div>
              <div class="dstat"><div class="dstat-icon">{ic("check-circle", 22)}</div><div class="dstat-k">Auto-Approved</div><div class="dstat-v" style="color:var(--green)">{s.auto_approved}</div></div>
              <div class="dstat"><div class="dstat-icon">{ic("user", 22)}</div><div class="dstat-k">Human-Approved</div><div class="dstat-v" style="color:var(--blue)">{s.human_approved}</div></div>
              <div class="dstat"><div class="dstat-icon">{ic("x-circle", 22)}</div><div class="dstat-k">Rejected</div><div class="dstat-v" style="color:var(--red)">{s.rejected}</div></div>
            </div>""", unsafe_allow_html=True)


            # Category breakdown
            cat_counts = {}
            for a in ans:
                for q in st.session_state.questions:
                    if q.id == a.question_id:
                        cat_counts[q.category] = cat_counts.get(q.category, 0) + 1
                        break
            if cat_counts:
                cat_html = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px">'
                cat_icons_2 = {"technical": "cpu", "certification": "shield-check", "legal": "scale", "data-privacy": "globe", "general": "file"}
                for cat, cnt in sorted(cat_counts.items()):
                    cat_html += f'<span class="chip ct">{ic(cat_icons_2.get(cat, "file"), 12)} {cat.replace("-", " ")}: {cnt}</span>'
                cat_html += '</div>'
                st.markdown(cat_html, unsafe_allow_html=True)

            # Three-column actions
            aC, bC, cC = st.columns(3)
            with aC:
                st.markdown(f"""<div class="acard"><div class="acard-head"><div class="acard-ic" style="background:rgba(99,102,241,.08);color:#8FA2FF">{ic("download", 20)}</div><div><div class="acard-t">Export Workbook</div><div class="acard-sub">Complete .xlsx with all Q&A</div></div></div>""", unsafe_allow_html=True)
                tmp = export_workbook(ans, filename="trustloop_export.xlsx")
                st.download_button("Download .xlsx", data=io.BytesIO(tmp.read_bytes()),
                                   file_name="trustloop_export.xlsx", type="primary", use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

            with bC:
                em = draft_prospect_email(ans)
                fl, _, rest = em.partition("\n\n")
                subj = fl.replace("Subject: ", "")
                st.markdown(f"""<div class="acard"><div class="acard-head"><div class="acard-ic" style="background:rgba(168,85,247,.08);color:#C4B5FD">{ic("mail", 20)}</div><div><div class="acard-t">Prospect Email</div><div class="acard-sub">Ready to send</div></div></div>
                <div class="email-mock"><div class="email-bar"><b>Subject:</b> {subj}</div><div class="email-body">{rest}</div></div></div>""", unsafe_allow_html=True)

            with cC:
                sb = build_slack_notification(ans)
                now = time.strftime("%I:%M %p")
                st.markdown(f"""<div class="acard"><div class="acard-head"><div class="acard-ic" style="background:rgba(52,211,153,.08);color:#34D399">{ic("message", 20)}</div><div><div class="acard-t">Slack Notification</div><div class="acard-sub">#deals channel</div></div></div>
                <div class="slack-mock"><div class="slack-row"><div class="slack-av" style="padding:0;overflow:hidden;background:transparent">{_logo(36, "slack")}</div><div><div><span class="slack-name">TrustLoop</span><span class="slack-time">{now}</span></div><div class="slack-body">{sb}</div></div></div></div></div>""", unsafe_allow_html=True)
                if st.button("Send to Slack", use_container_width=True, key="send_slack"):
                    result = send_slack_notification(ans)
                    if result.get("delivered"):
                        st.success("Delivered to Slack.")
                        db.add_event(run_id=st.session_state.get("run_id"), actor=_reviewer(),
                                     action="slack_sent", details={"channel": "#deals"})
                    elif result.get("dry_run"):
                        st.info("Dry run — set SLACK_WEBHOOK_URL to deliver for real.")
                    else:
                        st.error(result.get("detail", "Delivery failed."))

    # ── ANALYTICS ──
    elif view == "analytics":
        st.markdown("""<div class="tab-head"><div class="tab-head-t">Analytics</div>
          <div class="tab-head-s">Automation performance across all runs — auto-resolution trend, guardrail activity, and confidence by category.</div></div>""", unsafe_allow_html=True)
        rows = db.analytics_rows()
        data = compute_analytics(rows)
        if not data["has_data"]:
            st.markdown(f"""<div class="empty"><div class="empty-ic">{ic("chart", 44)}</div><div class="empty-t">No analytics yet</div><div class="empty-sub">Complete a run (or load the demo) — metrics appear here automatically.</div></div>""", unsafe_allow_html=True)
        else:
            ov = data["overview"]
            st.markdown(f"""<div class="dgrid">
              <div class="dstat"><div class="dstat-icon">{ic("file", 22)}</div><div class="dstat-k">Answers processed</div><div class="dstat-v" style="color:var(--text)">{ov['total_answers']}</div></div>
              <div class="dstat"><div class="dstat-icon">{ic("zap", 22)}</div><div class="dstat-k">Resolution rate</div><div class="dstat-v" style="color:var(--green)">{ov['resolution_rate']}%</div></div>
              <div class="dstat"><div class="dstat-icon">{ic("chart", 22)}</div><div class="dstat-k">Avg confidence</div><div class="dstat-v" style="color:var(--primary-light)">{int(ov['avg_confidence'] * 100)}%</div></div>
              <div class="dstat"><div class="dstat-icon">{ic("edit", 22)}</div><div class="dstat-k">Human edit rate</div><div class="dstat-v" style="color:var(--amber)">{ov['edit_rate_pct']}%</div></div>
            </div>""", unsafe_allow_html=True)

            ch1, ch2 = st.columns(2)
            with ch1:
                st.markdown('<div class="answer-section-lbl">Auto-resolution rate per run (%)</div>', unsafe_allow_html=True)
                trend = data["auto_rate_trend"]
                if len(trend) >= 1:
                    df_t = pd.DataFrame(trend)
                    df_t["label"] = [f"Run {i + 1}" for i in range(len(df_t))]
                    st.bar_chart(
                        df_t.set_index("label")["rate_pct"],
                        height=240,
                        color="#34d399",
                    )
                else:
                    st.caption("One run completed so far — trend appears after more runs.")
            with ch2:
                st.markdown('<div class="answer-section-lbl">Guardrail triggers by type</div>', unsafe_allow_html=True)
                if data["flag_frequency"]:
                    df_f = pd.DataFrame(data["flag_frequency"]).set_index("label")
                    st.bar_chart(df_f["count"], height=240, color="#fbbf24")
                else:
                    st.caption("No guardrails triggered across stored runs.")

            st.markdown('<div class="answer-section-lbl">Average confidence by category</div>', unsafe_allow_html=True)
            if data["confidence_by_category"]:
                df_c = pd.DataFrame(
                    [{"Category": k.replace("-", " ").title(), "AvgConfidence": v}
                     for k, v in data["confidence_by_category"].items()]
                ).set_index("Category")
                st.bar_chart(df_c, height=220, color="#818cf8")

            if data["most_flagged_questions"]:
                st.markdown('<div class="answer-section-lbl">Most-flagged questions</div>', unsafe_allow_html=True)
                df_q = pd.DataFrame(data["most_flagged_questions"])
                df_q = df_q.rename(columns={
                    "question": "Question", "flag_count": "Flag events",
                    "seen_in_runs": "Times seen",
                })
                st.dataframe(df_q[["Question", "Flag events", "Times seen"]],
                             use_container_width=True, hide_index=True)

    # ── AUDIT ──
    elif view == "audit":
        st.markdown("""<div class="tab-head"><div class="tab-head-t">Audit trail</div>
          <div class="tab-head-s">Immutable record of every run, decision, and actor. Export for compliance reviews.</div></div>""", unsafe_allow_html=True)
        runs = db.list_runs(limit=30)
        if not runs:
            st.markdown(f"""<div class="empty"><div class="empty-ic">{ic("shield-check", 44)}</div><div class="empty-t">Audit log is empty</div><div class="empty-sub">Run the pipeline or load the demo — every action is recorded here.</div></div>""", unsafe_allow_html=True)
        else:
            c1, c2 = st.columns([3, 1])
            with c1:
                sel_run = st.selectbox(
                    "Run",
                    runs,
                    format_func=lambda r: (
                        f"{r['run_id']} · {r['created_at'][:16].replace('T', ' ')} · "
                        f"{r['status']} · {r.get('answer_count', 0)} items"
                    ),
                    label_visibility="collapsed",
                )
            with c2:
                csv_all = db.export_audit_csv(Path("exports") / "trustloop_audit_full.csv")
                if csv_all:
                    st.download_button(
                        "Export full audit CSV",
                        data=csv_all.read_bytes(),
                        file_name="trustloop_audit.csv",
                        use_container_width=True,
                    )

            answers = db.get_run_answers(sel_run["run_id"])
            if answers:
                df_a = pd.DataFrame([{
                    "Question": a["question_text"],
                    "Status": a["status"],
                    "Confidence": f"{a['confidence']:.2f}",
                    "Decided by": a["decided_by"],
                    "Edited": "Yes" if a.get("was_edited") else "",
                    "Flags": "; ".join(f.split("]")[0] + "]" for f in a["risk_flags"]) or "—",
                } for a in answers])
                st.dataframe(df_a, use_container_width=True, hide_index=True)

            st.markdown('<div class="answer-section-lbl" style="margin-top:14px">Event log</div>', unsafe_allow_html=True)
            events = db.get_run_events(run_id=sel_run["run_id"], limit=100)
            if events:
                ev_rows = ""
                for e in reversed(events):
                    qid = f'<span class="cite">{e["question_id"]}</span>' if e.get("question_id") else ""
                    detail = e.get("details") or {}
                    det_s = ", ".join(f"{k}={v}" for k, v in list(detail.items())[:3])
                    ev_rows += (
                        f'<div class="qrow"><div class="qrow-n">{e["ts"][11:19]}</div>'
                        f'<div class="qrow-t"><b>{e["actor"]}</b> · {e["action"]} {qid}'
                        + (f' <span style="color:var(--text3)">({det_s})</span>' if det_s else "")
                        + "</div></div>"
                    )
                st.markdown(f'<div class="qlist">{ev_rows}</div>', unsafe_allow_html=True)

    # ── KB ──
    elif view == "kb":
        st.markdown("""<div class="tab-head"><div class="tab-head-t">Knowledge base</div>
          <div class="tab-head-s">Approved policy sources used by the research agent. Every draft answer cites documents from this base.</div></div>""", unsafe_allow_html=True)
        with st.expander("+ Add a live document", expanded=False):
            st.caption(
                "Upload a .md or .txt policy doc — the RAG index rebuilds "
                "immediately and new answers can cite it. No restart needed."
            )
            up = st.file_uploader(
                "Policy document", type=["md", "txt"], key="kb_upload"
            )
            if up is not None and st.button(
                "Add to knowledge base", type="primary", key="kb_ingest"
            ):
                try:
                    text = up.getvalue().decode("utf-8")
                except UnicodeDecodeError:
                    st.error("File must be UTF-8 encoded text.")
                else:
                    try:
                        info = ingest_document(up.name, text)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        verb = "Added" if info["created"] else "Updated"
                        st.success(
                            f"{verb} {info['filename']} — {info['chunks']} chunk(s). "
                            f"Index now holds {info['total_chunks']} chunks across "
                            f"{info['total_documents']} documents."
                        )
                        st.rerun()
        kb = Path("kb")
        docs = list_documents(kb)
        if docs:
            total_chunks = sum(d["chunks"] for d in docs)
            st.caption(
                f"{len(docs)} documents · {total_chunks} chunks indexed"
            )
            items = ""
            for d in docs:
                f = kb / d["filename"]
                try:
                    c = f.read_text(encoding="utf-8")
                except OSError:
                    continue
                title = c.split("\n")[0].replace("# ", "")
                desc_lines = [
                    line.strip()
                    for line in c.split("\n")[1:4]
                    if line.strip() and not line.startswith("#")
                ]
                desc = " ".join(desc_lines)[:120]
                tags = []
                if "security" in title.lower():
                    tags.append("security")
                if "policy" in title.lower():
                    tags.append("policy")
                if "compliance" in title.lower() or "cert" in title.lower():
                    tags.append("compliance")
                if "data" in title.lower():
                    tags.append("data")
                if "incident" in title.lower() or "continuity" in title.lower():
                    tags.append("operations")
                tags_html = "".join(f'<span class="kbcard-tag">{t}</span>' for t in tags[:3])
                items += f'<div class="kbcard"><div class="kbcard-name">{ic("file", 13)} {d["filename"]}</div><div class="kbcard-title">{title}</div><div class="kbcard-desc">{desc}…</div><div class="kbcard-tags">{tags_html}</div></div>'
            st.markdown(f'<div class="kbgrid">{items}</div>', unsafe_allow_html=True)


    # Auto-run pipeline for demo — rerun at the very end of script to allow full render
    if st.session_state.get("auto_run") and st.session_state.pipe_stage < 4:
        time.sleep(0.6)
        st.rerun()

# Enterprise theme wins over all earlier style blocks (rendered last).
st.markdown(CSS_ENTERPRISE, unsafe_allow_html=True)

