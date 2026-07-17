"""TrustLoop — Streamlit UI with space-themed landing page and rich demo experience."""

from __future__ import annotations

import io
import time
import random
from pathlib import Path

import pandas as pd
import streamlit as st

from actions import (
    build_slack_notification,
    draft_prospect_email,
    export_workbook,
    summarize_run,
    send_prospect_email,
)
from agents import parse_questionnaire
from config import COMPANY_NAME, PROSPECT_NAME, USE_LLM, LLM_PROVIDER
from graph import run_pipeline
from models import Answer

st.set_page_config(page_title="TrustLoop", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")

random.seed(42)

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

/* ═══ VARIABLES ═══ */
:root{
  --bg:#06060F; --bg2:#0A0A1A; --bg3:#0F0F24;
  --text:#e2e8f0; --text2:#94a3b8; --text3:#5a6478;
  --primary:#6366f1; --primary-light:#818cf8; --primary-dark:#4f46e5;
  --accent:#a855f7; --accent2:#c084fc;
  --green:#34d399; --amber:#fbbf24; --red:#ef4444; --blue:#38bdf8;
  --glass:rgba(255,255,255,.02); --glass-border:rgba(255,255,255,.04);
  --radius:12px; --radius-sm:8px; --radius-lg:16px;
}

/* ═══ LANDING NAV ═══ */
.lnav{
  position:fixed;top:0;left:0;right:0;z-index:1000;
  display:flex;align-items:center;justify-content:space-between;
  padding:0 32px;height:56px;
  background:rgba(6,6,15,.7);backdrop-filter:blur(24px) saturate(1.4);
  border-bottom:1px solid rgba(255,255,255,.04);
  transition:transform .3s ease,background .3s ease;
}
.lnav-brand{display:flex;align-items:center;gap:8px;font-size:16px;font-weight:800;color:var(--text);text-decoration:none}
.lnav-brand-ic{width:28px;height:28px;border-radius:7px;background:linear-gradient(135deg,var(--primary),var(--primary-dark));display:flex;align-items:center;justify-content:center;font-size:14px}
.lnav-links{display:flex;align-items:center;gap:20px}
.lnav-links a{font-size:12.5px;font-weight:500;color:var(--text3);text-decoration:none;transition:color .2s}
.lnav-links a:hover{color:var(--text)}
.lnav-cta{
  padding:9px 20px;border-radius:9px;font-size:12.5px;font-weight:700;
  background:linear-gradient(135deg,#818cf8,#6366f1 45%,#4f46e5);
  color:#ffffff!important;-webkit-text-fill-color:#ffffff!important;
  text-decoration:none!important;transition:all .2s;
  box-shadow:0 2px 16px rgba(99,102,241,.4),inset 0 1px 0 rgba(255,255,255,.18)
}
.lnav-cta:hover{transform:translateY(-1px);box-shadow:0 6px 24px rgba(99,102,241,.55);color:#ffffff!important;-webkit-text-fill-color:#ffffff!important}

/* ═══ LANDING ═══ */
.landing{position:relative;width:100%;min-height:100vh;overflow:hidden;background:var(--bg);padding-top:56px}
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
  display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:56px;
  animation:fadeUp .7s ease .4s both;max-width:700px;width:100%
}
.hero-stat{
  text-align:center;padding:22px 14px;border-radius:14px;
  background:var(--glass);border:1px solid var(--glass-border);
  backdrop-filter:blur(8px);transition:all .3s ease
}
.hero-stat:hover{background:rgba(255,255,255,.04);transform:translateY(-2px)}
.hero-stat-val{font-size:30px;font-weight:900;letter-spacing:-.03em;line-height:1}
.hero-stat-val.v1{color:var(--primary-light)}
.hero-stat-val.v2{color:var(--accent)}
.hero-stat-val.v3{color:var(--green)}
.hero-stat-val.v4{color:var(--amber)}
.hero-stat-lbl{font-size:11px;color:var(--text3);margin-top:6px;font-weight:500}

@keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}

/* Sections */
.sec{position:relative;z-index:5;padding:100px 48px;max-width:1120px;margin:0 auto}
.sec-wide{background:rgba(6,6,15,.95);max-width:100%;padding-left:calc((100% - 1072px)/2);padding-right:calc((100% - 1072px)/2)}
.sec-tag{
  display:inline-block;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.15em;
  color:var(--primary-light);padding:5px 12px;border-radius:5px;
  background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.12);margin-bottom:16px
}
.sec-title{font-size:clamp(26px,3.8vw,40px);font-weight:900;letter-spacing:-.035em;color:var(--text);margin-bottom:12px;line-height:1.15}
.sec-desc{font-size:14.5px;color:var(--text3);line-height:1.65;max-width:520px;margin-bottom:44px}

/* Steps */
.steps-wrapper{position:relative;padding:10px 0}
.steps-connector{position:absolute;top:46px;left:calc(12.5% + 36px);right:calc(12.5% + 36px);height:2px;
  background:linear-gradient(90deg,var(--primary),var(--accent),var(--amber),var(--green));
  opacity:.15;z-index:0}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;position:relative;z-index:1}
.step{
  padding:28px 22px 24px;border-radius:16px;
  background:var(--glass);border:1px solid var(--glass-border);
  backdrop-filter:blur(8px);transition:all .35s ease;position:relative;overflow:hidden
}
.step::after{content:'';position:absolute;inset:0;border-radius:16px;padding:1px;
  background:linear-gradient(135deg,transparent 40%,rgba(99,102,241,.12));
  -webkit-mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);
  mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);
  -webkit-mask-composite:xor;mask-composite:exclude;opacity:0;transition:opacity .4s}
.step:hover::after{opacity:1}
.step:hover{transform:translateY(-4px);box-shadow:0 16px 48px rgba(0,0,0,.4)}
.step-n{
  width:38px;height:38px;border-radius:12px;display:flex;align-items:center;justify-content:center;
  font-size:13px;font-weight:800;margin-bottom:16px;position:relative;z-index:1
}
.step-n.n1{background:rgba(99,102,241,.12);color:var(--primary-light)}
.step-n.n2{background:rgba(168,85,247,.12);color:var(--accent2)}
.step-n.n3{background:rgba(251,191,36,.12);color:var(--amber)}
.step-n.n4{background:rgba(52,211,153,.12);color:var(--green)}
.step h3{font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px}
.step p{font-size:12.5px;color:var(--text3);line-height:1.55}

/* Features */
.feats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.feat{
  padding:26px 22px;border-radius:14px;
  background:var(--glass);border:1px solid var(--glass-border);
  backdrop-filter:blur(8px);transition:all .3s ease;position:relative;overflow:hidden
}
.feat:hover{border-color:rgba(99,102,241,.18);background:rgba(255,255,255,.03);transform:translateY(-2px)}
.feat-ic{
  width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;
  font-size:20px;margin-bottom:14px;transition:all .3s ease
}
.feat:hover .feat-ic{transform:scale(1.1)}
.feat-ic.i1{background:rgba(99,102,241,.1)}
.feat-ic.i2{background:rgba(168,85,247,.1)}
.feat-ic.i3{background:rgba(52,211,153,.1)}
.feat-ic.i4{background:rgba(251,191,36,.1)}
.feat-ic.i5{background:rgba(244,114,182,.1)}
.feat-ic.i6{background:rgba(14,165,233,.1)}
.feat h3{font-size:14px;font-weight:700;color:var(--text);margin-bottom:5px}
.feat p{font-size:12px;color:var(--text3);line-height:1.55}

/* Dashboard mockup */
.mockup-wrap{background:var(--glass);border:1px solid var(--glass-border);border-radius:20px;overflow:hidden;backdrop-filter:blur(8px);margin-top:30px}
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
.mockup-right-btn{padding:6px 14px;border-radius:6px;font-size:10px;font-weight:600;border:none}
.mockup-right-btn.green{background:rgba(52,211,153,.1);color:var(--green)}
.mockup-right-btn.red{background:rgba(239,68,68,.08);color:var(--red)}

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
.cta{text-align:center;padding:80px 40px 60px;position:relative;z-index:5}
.cta h2{font-size:clamp(24px,3vw,34px);font-weight:900;color:var(--text);margin-bottom:12px;letter-spacing:-.03em}
.cta p{font-size:14px;color:var(--text3);margin-bottom:28px;max-width:420px;margin-left:auto;margin-right:auto}

/* Footer */
.foot{
  border-top:1px solid var(--glass-border);padding:24px 48px;
  display:flex;justify-content:space-between;color:var(--text3);
  font-size:11.5px;position:relative;z-index:5;background:rgba(6,6,15,.95)
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
  padding:0 20px;height:44px;
  background:rgba(6,6,15,.8);backdrop-filter:blur(20px) saturate(1.4);
  border-bottom:1px solid var(--glass-border)
}
.appbar-brand{display:flex;align-items:center;gap:7px;font-size:14px;font-weight:700;color:var(--text);text-decoration:none}
.appbar-brand-ic{width:24px;height:24px;border-radius:7px;background:linear-gradient(135deg,var(--primary),var(--primary-dark));display:flex;align-items:center;justify-content:center;font-size:12px}
.appbar-actions{display:flex;align-items:center;gap:8px}
.appbar-badge{
  display:flex;align-items:center;gap:4px;padding:3px 10px;border-radius:5px;
  font-size:10px;font-weight:600;background:rgba(99,102,241,.08);color:var(--primary-light);border:1px solid rgba(99,102,241,.12)
}
.appbar-home{padding:3px 10px;border-radius:5px;cursor:pointer;font-size:10px;font-weight:500;color:var(--text3);background:var(--glass);border:1px solid var(--glass-border);transition:all .2s}

/* Pipeline — compact horizontal strip */
.pipe-strip{
  display:flex;align-items:center;justify-content:center;gap:0;
  max-width:700px;margin:24px auto 12px!important;
  padding:12px 24px 8px;position:relative;z-index:5
}
.pipe-node{display:flex;flex-direction:column;align-items:center;gap:6px;position:relative;flex-shrink:0}
.pipe-ic{
  width:50px;height:50px;border-radius:14px;display:flex;align-items:center;justify-content:center;
  font-size:22px;border:1.5px solid var(--glass-border);background:rgba(15,23,42,.5);
  transition:all .4s ease;position:relative
}
.pipe-node.active .pipe-ic{
  border-color:rgba(99,102,241,.4);background:rgba(99,102,241,.07);
  box-shadow:0 0 18px rgba(99,102,241,.12);animation:pipePulse 2s ease-in-out infinite
}
.pipe-node.done .pipe-ic{
  border-color:rgba(52,211,153,.25);background:rgba(52,211,153,.07)
}
.pipe-lbl{font-size:11px;font-weight:600;color:var(--text3);transition:color .3s;text-align:center;white-space:nowrap;letter-spacing:0.02em}
.pipe-node.active .pipe-lbl{color:var(--primary-light)}
.pipe-node.done .pipe-lbl{color:var(--green)}
.pipe-seg{width:36px;height:2px;background:rgba(255,255,255,.03);margin:0 4px;margin-bottom:18px;transition:all .5s ease;border-radius:999px;flex-shrink:0}
.pipe-seg.active{background:linear-gradient(90deg,var(--green),var(--primary-light));box-shadow:0 0 8px rgba(99,102,241,.1)}
.pipe-seg.done{background:var(--green)}
@keyframes pipePulse{0%,100%{box-shadow:0 0 12px rgba(99,102,241,.08)}50%{box-shadow:0 0 22px rgba(99,102,241,.15)}}
 
.pipe-stage-info{
  text-align:center;font-size:11px;color:var(--text3);margin-top:4px;padding:0 20px 0;
  animation:fadeUp .3s ease both;opacity:.8
}
.pipe-stage-info strong{color:var(--text2)}

/* Dashboard bar — combined chips + quick stats */
.dash-bar{
  display:flex;align-items:center;gap:8px;padding:6px 20px 8px;margin-bottom:16px!important;position:relative;z-index:5;flex-wrap:wrap
}
.dash-bar .chip{
  display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:6px;
  font-size:10px;font-weight:500
}
.dash-bar .chip.ct{background:rgba(255,255,255,.03);color:var(--text3);border:1px solid var(--glass-border)}
.dash-bar .chip.co{background:rgba(52,211,153,.06);color:var(--green);border:1px solid rgba(52,211,153,.1)}
.dash-bar .chip.cw{background:rgba(251,191,36,.06);color:var(--amber);border:1px solid rgba(251,191,36,.1)}
.dash-bar .chip.ci{background:rgba(14,165,233,.06);color:var(--blue);border:1px solid rgba(14,165,233,.1)}
.dash-bar .chip.cr{background:rgba(239,68,68,.06);color:var(--red);border:1px solid rgba(239,68,68,.1)}

/* Upload tab */
.upload-zone{text-align:center;padding:50px 20px}
.upload-ic{font-size:52px;margin-bottom:14px;opacity:.6}
.upload-h{font-size:18px;font-weight:700;color:var(--text);margin-bottom:6px}
.upload-sub{font-size:12.5px;color:var(--text3);margin-bottom:24px}

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
  display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:9px;
  background:var(--glass);border:1px solid var(--glass-border);
  transition:all .15s ease;cursor:default
}
.qrow:hover{background:rgba(255,255,255,.03);border-color:rgba(255,255,255,.06)}
.qrow-n{font-size:10px;font-weight:600;color:var(--text3);min-width:20px;font-family:'JetBrains Mono',monospace}
.qrow-t{flex:1;font-size:12.5px;color:var(--text2);line-height:1.3}
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
  gap:3px;background:var(--glass);padding:3px;border-radius:8px;
  border:1px solid var(--glass-border);margin-bottom:12px
}
.stTabs [data-baseweb="tab"]{
  background:transparent!important;color:var(--text3)!important;border-radius:7px!important;
  padding:6px 14px!important;font-weight:500!important;font-size:11.5px!important;
  border:none!important;transition:all .15s!important
}
.stTabs [data-baseweb="tab"]:hover{color:var(--text)!important;background:rgba(255,255,255,.02)!important}
.stTabs [aria-selected="true"]{
  color:var(--text)!important;background:rgba(99,102,241,.08)!important;
  box-shadow:0 0 12px rgba(99,102,241,.06)!important
}
.stButton>button{
  border-radius:8px!important;font-weight:600!important;font-size:12px!important;
  transition:all .15s!important;border:none!important;
  background:rgba(255,255,255,.03)!important;color:var(--text2)!important;
  border:1px solid var(--glass-border)!important
}
.stButton>button:hover{transform:translateY(-1px)!important;border-color:rgba(255,255,255,.08)!important}
.stButton>button[kind="primary"]{
  background:linear-gradient(135deg,var(--primary),var(--primary-dark))!important;
  color:#fff!important;border:none!important
}
.stTextArea textarea{
  background:rgba(15,23,42,.5)!important;border:1px solid var(--glass-border)!important;
  border-radius:8px!important;color:var(--text2)!important;font-size:12px!important;
  line-height:1.5!important;caret-color:var(--primary-light)!important
}
.stTextArea textarea:focus{border-color:rgba(99,102,241,.3)!important}
.stSelectbox [data-baseweb="select"]{
  background:rgba(15,23,42,.5)!important;border-color:var(--glass-border)!important;
  border-radius:7px!important;font-size:12px!important
}
[data-testid="stFileUploaderDropzone"]{
  background:rgba(15,23,42,.4)!important;border:1.5px dashed rgba(99,102,241,.15)!important;
  border-radius:12px!important;transition:all .2s!important
}
[data-testid="stFileUploaderDropzone"]:hover{border-color:rgba(99,102,241,.3)!important}
[data-testid="stSidebar"]{
  background:rgba(6,6,15,.95)!important;
  border-right:1px solid var(--glass-border)!important;
  backdrop-filter:blur(12px)!important
}
.stSidebar .stButton>button{font-size:11px!important;padding:5px 12px!important}

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
.block-container { padding: 16px 28px 28px 28px !important; max-width: 100% !important; }

/* Allow modern gap between layout sections */
.stVerticalBlock {
  gap: 16px !important;
}
.stHorizontalBlock {
  gap: 16px !important;
}

/* Add margins to separate major panels and text blocks */
.element-container {
  margin-bottom: 12px !important;
}

/* Spacing and typography within markdown text */
.stMarkdown, .stMarkdown > div {
  line-height: 1.5 !important;
}
.stMarkdown p {
  margin-top: 6px !important;
  margin-bottom: 6px !important;
}

/* SPACIOUS REVIEW TAB ELEMENTS */
.rpanel {
  padding: 28px 32px !important;
  margin-bottom: 24px !important;
}
.rpanel-q {
  margin-top: 12px !important;
  margin-bottom: 24px !important;
  padding: 20px 24px !important;
  line-height: 1.6 !important;
}

/* Spacing out confidence score & status cards */
.conf-grid {
  gap: 16px !important;
  margin-top: 16px !important;
  margin-bottom: 24px !important;
}
.conf-card {
  padding: 20px 22px !important;
}
.conf-card-top {
  margin-bottom: 12px !important;
}

/* Spacing out risk flags list */
.flags {
  gap: 12px !important;
  margin-top: 12px !important;
  margin-bottom: 24px !important;
}
.flag {
  padding: 12px 18px !important;
  line-height: 1.6 !important;
}

/* Spacing out evidence citations */
.cites {
  gap: 10px !important;
  margin-top: 12px !important;
  margin-bottom: 24px !important;
}
.cite {
  padding: 6px 14px !important;
}

/* Spacing out draft answer editor label and area */
.answer-section {
  margin-top: 24px !important;
  margin-bottom: 14px !important;
}
.answer-section-lbl {
  margin-bottom: 10px !important;
}
[data-testid="stTextArea"] {
  margin-top: 8px !important;
  margin-bottom: 24px !important;
}

/* Spacing out the bottom action buttons */
.btn-approve, .btn-edit, .btn-reject {
  margin-top: 8px !important;
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
    }.items():
        st.session_state.setdefault(k, v)


def _ans(qid):
    for a in st.session_state.answers:
        if a.question_id == qid:
            return a
    return None


def _upd(ans):
    lst = st.session_state.answers
    for i, a in enumerate(lst):
        if a.question_id == ans.question_id:
            lst[i] = ans
            break
    st.session_state.review_queue = [a.question_id for a in lst if a.status == "needs_review"]
    if not st.session_state.review_queue:
        st.session_state.final_status = "completed"
        st.session_state.pipe_stage = 4


def _demo():
    from samples.demo_data import DEMO_QUESTIONS
    st.session_state.update(
        questions=DEMO_QUESTIONS, answers=[], review_queue=[],
        demo=True, final_status="processing", pipe_stage=0,
        balloons_shown=False, total_review_items=0,
        auto_run=True, auto_run_start=time.time(), pipeline_done=False,
    )

def _load_demo_answers():
    from samples.demo_data import DEMO_ANSWERS, DEMO_REVIEW_QUEUE
    if not st.session_state.answers:
        st.session_state.update(
            answers=DEMO_ANSWERS, review_queue=list(DEMO_REVIEW_QUEUE),
            final_status="reviewing" if DEMO_REVIEW_QUEUE else "completed",
            total_review_items=len(DEMO_REVIEW_QUEUE),
        )


def _fc(f):
    if "[CERT_WARNING]" in f:
        return "fp"
    if "[LEGAL_RISK]" in f:
        return "fd"
    if "[DATA_RESIDENCY]" in f:
        return "fw"
    return "fi"


def _fi(f):
    m = {"CERT_WARNING": "🎓", "LEGAL_RISK": "⚖️", "DATA_RESIDENCY": "🌍",
         "MISSING_EVIDENCE": "🔍", "LOW_CONFIDENCE": "📉", "ROUTING": "🧭"}
    for k, v in m.items():
        if k in f:
            return v
    return "⚠️"


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
qp = st.query_params
if qp.get("demo") == "1" and st.session_state.page == "landing":
    _demo()
    st.session_state.page = "app"
    st.rerun()

# ── LANDING ──
if st.session_state.page == "landing":
    st.markdown(CSS_LANDING, unsafe_allow_html=True)
    stars = ""
    for _ in range(180):
        x, y = random.randint(0, 100), random.randint(0, 100)
        s = random.uniform(0.5, 2)
        o = random.uniform(0.25, 0.95)
        stars += f'<div class="star" style="left:{x}%;top:{y}%;width:{s}px;height:{s}px;opacity:{o};animation:twinkle{random.randint(2,5)}s ease-in-out infinite {random.random()}s"></div>'

    st.markdown(f"""<div class="landing">
<nav class="lnav">
<a href="#" class="lnav-brand"><div class="lnav-brand-ic">🛡️</div>TrustLoop</a>
<div class="lnav-links">
<a href="#how">How it works</a>
<a href="#features">Features</a>
<a href="#preview">Preview</a>
<a href="?demo=1" class="lnav-cta">Launch Demo →</a>
</div>
</nav>

<div class="stars">{stars}</div>
<div class="nebula n1"></div><div class="nebula n2"></div>
<div class="space-grid"></div>
<div class="planet p1"></div>
<div class="shoot s1"></div><div class="shoot s2"></div>

<div class="hero">
<div class="hero-inner">
<div class="hero-badge"><span class="hero-badge-dot"></span> AI-Powered Security Automation</div>
<h1 class="hero-title">Security questionnaires<br><span class="g1">automated</span>, <span class="g3">grounded</span>, <span class="g2">verified</span></h1>
<p class="hero-sub">Multi-agent AI parses questionnaires, retrieves grounded evidence from your knowledge base, runs compliance guardrails, and routes risky items to human reviewers — all in under 2 minutes.</p>
<div class="hero-btns">
<a href="?demo=1" class="btn btn-fill">🚀 Launch Interactive Demo</a>
<a href="#how" class="btn btn-ghost">See how it works ↓</a>
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
<div class="feat"><div class="feat-ic i1">📚</div><h3>RAG Knowledge Base</h3><p>10 policy documents. Every answer grounded in source material — no hallucination risk.</p></div>
<div class="feat"><div class="feat-ic i2">🛡️</div><h3>Compliance Guardrails</h3><p>Automated checks for certification claims, legal exposure, data residency, confidence thresholds, and more.</p></div>
<div class="feat"><div class="feat-ic i3">⚡</div><h3>Auto-Approval</h3><p>High-confidence answers with no risk flags auto-approve. ~55% never need human review.</p></div>
<div class="feat"><div class="feat-ic i4">👤</div><h3>Human-in-the-Loop</h3><p>Risky items route with confidence scores, risk flags, and evidence. Approve, edit, or reject in one click.</p></div>
<div class="feat"><div class="feat-ic i5">✉️</div><h3>Auto-Email</h3><p>Completed questionnaires emailed to prospects automatically when confidence exceeds threshold.</p></div>
<div class="feat"><div class="feat-ic i6">🔌</div><h3>REST API</h3><p>Programmatic access via FastAPI. Export to .xlsx, Slack notifications, integrate with your tools.</p></div>
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
<div class="mockup-tab-item">📥 Upload</div>
<div class="mockup-tab-item active">🧪 Review</div>
<div class="mockup-tab-item">📦 Deliver</div>
<div class="mockup-tab-item">📚 KB</div>
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
<div class="mockup-right-flag">⚠️ Acme SaaS does not hold HIPAA certification.</div>
<div class="mockup-right-edit">No. Acme SaaS is NOT HIPAA certified and does NOT sign Business Associate Agreements (BAAs). Customers must not store Protected Health Information (PHI) on the platform.</div>
<div class="mockup-right-acts">
<div class="mockup-right-btn green">✅ Approve</div>
<div class="mockup-right-btn">✏️ Edit</div>
<div class="mockup-right-btn red">❌ Reject</div>
</div>
</div>
</div>
</div>
</div>

<div class="cta">
<h2>Ready to automate?</h2>
<p>Try the live demo — 27 questions across 5 security categories, no sign-up required.</p>
<a href="?demo=1" class="btn btn-fill">🚀 Launch Demo Now</a>
</div>
<div class="foot">
<div>© 2026 TrustLoop</div>
<div style="display:flex;gap:16px;color:var(--text3)">
<span>LangGraph</span><span>·</span><span>RAG</span><span>·</span><span>Streamlit</span><span>·</span><span>FastAPI</span>
</div>
</div>
""", unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### 🚀 Launch Demo")
        st.markdown("Click below to start the interactive demo.")
        if st.button("🚀 Start Demo", use_container_width=True, type="primary"):
            _demo()
            st.session_state.page = "app"
            st.rerun()
        st.markdown("---")
        if USE_LLM:
            st.success(f"LLM: {LLM_PROVIDER.upper()}", icon="🤖")
        else:
            st.info("Offline mode (RAG only)", icon="⚡")


# ── APP ──
else:
    st.markdown(CSS_APP, unsafe_allow_html=True)
    # Generate stars for space background
    stars_html = ""
    for _ in range(150):
        x, y = random.randint(0, 100), random.randint(0, 100)
        s = random.uniform(0.5, 1.8)
        o = random.uniform(0.2, 0.9)
        stars_html += f'<div class="star" style="left:{x}%;top:{y}%;width:{s}px;height:{s}px;opacity:{o};animation:twinkle{random.randint(2,5)}s ease-in-out infinite {random.random()}s"></div>'

    st.markdown(f"""
    <div class="stars" style="z-index:0">{stars_html}</div>
    <div class="nebula n1"></div><div class="nebula n2"></div><div class="nebula n3"></div>
    <div class="space-grid"></div>
    <div class="planet p1"><div class="planet-ring"></div></div>
    <div class="shoot s1"></div><div class="shoot s2"></div>
    <div class="app-glow1"></div><div class="app-glow2"></div>
    """, unsafe_allow_html=True)

    # Sidebar — rendered first so it's always visible
    with st.sidebar:
        if st.button("← Home", use_container_width=True):
            st.session_state.page = "landing"
            st.rerun()
        st.markdown("---")
        if st.button("🚀 Load Demo", use_container_width=True):
            _demo()
            st.rerun()
        if st.button("📥 Load sample file", use_container_width=True):
            p = Path("samples/demo_questionnaire_full.txt")
            if p.exists():
                st.session_state.questions = parse_questionnaire(p.read_text())
                st.session_state.answers, st.session_state.review_queue = [], []
                st.session_state.step, st.session_state.demo = 1, False
                st.rerun()
        st.markdown("---")
        if st.session_state.answers:
            s = summarize_run(st.session_state.answers)
            st.caption("📊 Summary")
            st.markdown(f"""<div style="font-size:12px;line-height:1.8">
              <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">Total</span><span style="color:var(--text);font-weight:600">{s.total}</span></div>
              <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">Auto-approved</span><span style="color:var(--green);font-weight:600">{s.auto_approved}</span></div>
              <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">Needs review</span><span style="color:var(--amber);font-weight:600">{s.needs_review}</span></div>
              <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">Reviewed</span><span style="color:var(--blue);font-weight:600">{s.human_approved}</span></div>
              <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">Rejected</span><span style="color:var(--red);font-weight:600">{s.rejected}</span></div>
            </div>""", unsafe_allow_html=True)
            st.markdown("---")
        if USE_LLM:
            st.success(f"LLM: {LLM_PROVIDER.upper()}", icon="🤖")
        else:
            st.info("Offline", icon="⚡")

    # App bar
    st.markdown(f"""
    <div class="appbar">
      <a href="#" class="appbar-brand"><div class="appbar-brand-ic">🛡️</div>TrustLoop</a>
      <div class="appbar-actions">
        <span class="appbar-badge">🚀 {'Pipeline Running…' if st.session_state.get('auto_run') else 'Demo' if st.session_state.demo else 'Live'}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Pipeline — compact strip with stage info
    ps = st.session_state.pipe_stage
    nodes = [("📋", "Upload"), ("🔍", "Parse"), ("🧠", "Research"), ("🛡️", "Verify"), ("✅", "Deliver")]
    stage_descs = [
        "Upload your security questionnaire (.xlsx or .txt)",
        "Splitting questions and classifying into 5 security categories",
        "Querying knowledge base with RAG for grounded answers",
        "Running 7 compliance guardrails on each answer",
        "All items resolved — ready for delivery",
    ]
    stage_icons = ["📋", "⚡", "🔎", "🛡️", "🎯"]
    stage_info = stage_descs[ps] if 0 <= ps < len(stage_descs) else ""
    stage_icon = stage_icons[ps] if 0 <= ps < len(stage_icons) else ""
    h = '<div class="pipe-strip">'
    for i, (ic, lbl) in enumerate(nodes):
        cls = "done" if ps > i else ("active" if ps == i else "")
        if i > 0:
            seg = "done" if ps > i else ("active" if ps == i else "")
            h += f'<div class="pipe-seg {seg}"></div>'
        h += f'<div class="pipe-node {cls}"><div class="pipe-ic">{ic}</div><div class="pipe-lbl">{lbl}</div></div>'
    h += '</div>'
    if stage_info:
        h += f'<div class="pipe-stage-info">{stage_icon} <strong>{stage_info}</strong></div>'
    st.markdown(h, unsafe_allow_html=True)

    # Dashboard bar
    chips_html = ""
    if st.session_state.answers:
        s = summarize_run(st.session_state.answers)
        chips_html = f"""
          <span class="chip ct">📊 {s.total}</span>
          <span class="chip co">✅ {s.auto_approved}</span>
          <span class="chip cw">⏳ {s.needs_review}</span>
          <span class="chip ci">👤 {s.human_approved}</span>
          <span class="chip cr">❌ {s.rejected}</span>
        """
    if st.session_state.get("pipeline_done"):
        chips_html += '<span class="chip co" style="background:rgba(99,102,241,.08);color:var(--primary-light);border-color:rgba(99,102,241,.15)">🚀 Demo ready</span>'
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

    # Tabs
    t_up, t_rev, t_del, t_kb = st.tabs(["📥 Upload", "🧪 Review", "📦 Deliver", "📚 KB"])

    # ── UPLOAD TAB ──
    with t_up:
        if not st.session_state.questions:
            c1, c2, c3 = st.columns([1, 2, 1])
            with c2:
                st.markdown("""<div class="upload-zone"><div class="upload-ic">📋</div>
                  <div class="upload-h">Upload your security questionnaire</div>
                  <div class="upload-sub">Drop a .xlsx or .txt file, paste questions below, or load the demo from the sidebar</div></div>""", unsafe_allow_html=True)
                up = st.file_uploader("Upload", type=["xlsx", "txt"], label_visibility="collapsed")
                st.markdown('<div style="text-align:center;color:var(--text3);font-size:11.5px;margin:8px 0">— or paste questions below —</div>', unsafe_allow_html=True)
                paste = st.text_area("Paste", height=100, label_visibility="collapsed",
                                     placeholder="Do you encrypt data at rest?\nAre you HIPAA certified?\nWhere is customer data stored?")
                c1, c2 = st.columns(2)
                if c1.button("Parse Questionnaire", use_container_width=True, type="primary"):
                    raw = None
                    if up:
                        if up.name.lower().endswith(".xlsx"):
                            tmp = Path("./_u.xlsx")
                            tmp.write_bytes(up.getvalue())
                            st.session_state.questions = parse_questionnaire(tmp)
                            tmp.unlink(missing_ok=True)
                        else:
                            raw = up.getvalue().decode("utf-8", errors="ignore")
                    elif paste.strip():
                        raw = paste
                    if raw:
                        st.session_state.questions = parse_questionnaire(raw)
                    if st.session_state.questions:
                        st.session_state.step, st.session_state.demo = 1, False
                        st.rerun()
                    else:
                        st.warning("Nothing to parse.")
        else:
            qs = st.session_state.questions
            has_answers = bool(st.session_state.answers)

            if st.session_state.get("auto_run"):
                elapsed = time.time() - st.session_state.auto_run_start
                stage = st.session_state.pipe_stage
                if stage == 0:
                    st.markdown("""<div class="loading"><div class="loading-ic">🔄</div>
                      <div class="loading-t">Uploading questionnaire...</div>
                      <div class="loading-sub">Processing incoming file "questionnaire_enterprise.xlsx" (24 KB)...</div></div>""", unsafe_allow_html=True)
                elif stage == 1:
                    st.markdown("""<div class="loading"><div class="loading-ic">⚙️</div>
                      <div class="loading-t">Parsing & Classifying Questions...</div>
                      <div class="loading-sub">Classifying 27 questions across 5 compliance categories...</div></div>""", unsafe_allow_html=True)
                elif stage == 2:
                    pct = min(int((elapsed - 5.0) / 2.5 * 100), 100)
                    num_answered = int(len(qs) * (pct / 100))
                    st.markdown(f"""<div class="loading"><div class="loading-ic">🧠</div>
                      <div class="loading-t">Researching Grounded Answers ({num_answered}/{len(qs)})...</div>
                      <div class="loading-sub">Retrieving policy evidence and drafting answers from knowledge base...</div></div>""", unsafe_allow_html=True)
                    rows = ""
                    for idx, q in enumerate(qs):
                        if idx < num_answered:
                            status_text = "✅ Grounded"
                            status_cls = "auto"
                        elif idx == num_answered:
                            status_text = "🧠 Researching..."
                            status_cls = "review"
                        else:
                            status_text = "⏳ Pending"
                            status_cls = "general"
                        rows += f'<div class="qrow"><div class="qrow-n">{idx + 1}</div><div class="qrow-t">{q.text}</div><div class="qrow-c {q.category}">{q.category.replace("-", " ")}</div><div class="qrow-status {status_cls}">{status_text}</div></div>'
                    st.markdown(f'<div class="qlist">{rows}</div>', unsafe_allow_html=True)
                elif stage == 3:
                    st.markdown("""<div class="loading"><div class="loading-ic">🛡️</div>
                      <div class="loading-t">Running Compliance Guardrails...</div>
                      <div class="loading-sub">Validating certification claims, data residency, and confidence thresholds...</div></div>""", unsafe_allow_html=True)
                    _load_demo_answers()
                    rows = ""
                    for idx, q in enumerate(qs):
                        status_text = ""
                        status_cls = ""
                        a = _ans(q.id)
                        if a:
                            if a.status == "auto_approved":
                                status_text = "✅ Auto"
                                status_cls = "auto"
                            elif a.status == "needs_review":
                                status_text = "⏳ Review"
                                status_cls = "review"
                        rows += f'<div class="qrow"><div class="qrow-n">{idx + 1}</div><div class="qrow-t">{q.text}</div><div class="qrow-c {q.category}">{q.category.replace("-", " ")}</div>{"<div class=\"qrow-status " + status_cls + "\">" + status_text + "</div>" if status_text else ""}</div>'
                    st.markdown(f'<div class="qlist">{rows}</div>', unsafe_allow_html=True)
            else:
                if has_answers and st.session_state.demo:
                    n_review = len(st.session_state.review_queue)
                    st.markdown(f"""<div class="info-banner">
                      <div class="info-banner-ic">🚀</div>
                      <div class="info-banner-content">
                        <div class="info-banner-title">Demo loaded — {len(qs)} questions across 5 categories</div>
                        <div class="info-banner-sub">{'✅ ' + str(len(qs) - n_review) + ' auto-approved · ⏳ ' + str(n_review) + ' need review' if n_review else '✅ All auto-approved — check the Deliver tab'}</div>
                      </div>
                    </div>""", unsafe_allow_html=True)

                # Category distribution
                cats = {}
                for q in qs:
                    cats[q.category] = cats.get(q.category, 0) + 1
                cat_colors = {"technical": "rgba(99,102,241,.08)", "certification": "rgba(168,85,247,.08)",
                              "legal": "rgba(239,68,68,.08)", "data-privacy": "rgba(251,191,36,.08)", "general": "rgba(255,255,255,.04)"}
                cat_text = {"technical": "#a5b4fc", "certification": "#c084fc",
                            "legal": "#fca5a5", "data-privacy": "#fcd34d", "general": "#6b7a90"}
                bar_total = sum(cats.values()) or 1
                bar_html = '<div style="display:flex;gap:3px;height:6px;margin-bottom:14px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.02)">'
                for cat in ["technical", "certification", "data-privacy", "legal", "general"]:
                    if cat in cats:
                        pct = cats[cat] / bar_total * 100
                        bar_html += f'<div style="width:{pct}%;background:{cat_colors[cat]};min-width:4px" title="{cat}: {cats[cat]}"></div>'
                bar_html += '</div>'
                st.markdown(bar_html, unsafe_allow_html=True)

                # Question rows with search
                search_q = st.text_input("🔍", placeholder="Filter questions...", label_visibility="collapsed")
                filtered = qs
                if search_q:
                    filtered = [q for q in qs if search_q.lower() in q.text.lower()]

                rows = ""
                for i, q in enumerate(filtered):
                    status_text = ""
                    status_cls = ""
                    if has_answers:
                        a = _ans(q.id)
                        if a:
                            if a.status == "auto_approved":
                                status_text = "✅ Auto"
                                status_cls = "auto"
                            elif a.status == "needs_review":
                                status_text = "⏳ Review"
                                status_cls = "review"
                            elif a.status == "human_approved":
                                status_text = "👤 Done"
                                status_cls = "auto"
                            elif a.status == "rejected":
                                status_text = "❌ Rej"
                                status_cls = "review"
                    rows += f'<div class="qrow"><div class="qrow-n">{i + 1}</div><div class="qrow-t">{q.text}</div><div class="qrow-c {q.category}">{q.category.replace("-", " ")}</div>{"<div class=\"qrow-status " + status_cls + "\">" + status_text + "</div>" if status_text else ""}</div>'

                st.markdown(f'<div class="qlist">{rows}</div>', unsafe_allow_html=True)

                # Action buttons
                st.markdown("<br>", unsafe_allow_html=True)
                if has_answers and st.session_state.review_queue:
                    st.markdown(f"""<div style="text-align:center;padding:14px;background:rgba(251,191,36,.05);border:1px solid rgba(251,191,36,.12);border-radius:10px">
                      <div style="font-size:13px;font-weight:600;color:var(--amber);margin-bottom:4px">🎯 {len(st.session_state.review_queue)} item(s) need human review</div>
                      <div style="font-size:11px;color:var(--text3)">Switch to the <strong>Review</strong> tab to approve, edit, or reject.</div>
                    </div>""", unsafe_allow_html=True)
                elif has_answers and not st.session_state.review_queue:
                    st.success("✅ All items resolved! Check the Deliver tab.", icon="🎉")

                if not has_answers:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("▶ Run Pipeline", use_container_width=True, type="primary"):
                        st.session_state.pipe_stage = 1
                        st.session_state.demo = False
                        st.rerun()

            if st.session_state.pipe_stage == 1 and not st.session_state.demo:
                ph = st.empty()
                ph.markdown("""<div class="loading"><div class="loading-ic">⚡</div>
                  <div class="loading-t">Running multi-agent pipeline...</div>
                  <div class="loading-sub">Intake → Research → Compliance → Routing</div></div>""", unsafe_allow_html=True)
                raw = "\n".join(q.text for q in st.session_state.questions)
                state = run_pipeline(raw)
                st.session_state.questions = list(state["questions"])
                st.session_state.answers = list(state["answers"])
                st.session_state.review_queue = list(state["review_queue"])
                st.session_state.final_status = state["final_status"]
                st.session_state.run_complete = state["final_status"] == "completed"
                st.session_state.pipe_stage = 4 if not state["review_queue"] else 3
                st.session_state.step = 3 if not state["review_queue"] else 2
                ph.empty()
                st.rerun()

    # ── REVIEW TAB ──
    with t_rev:
        ans = st.session_state.answers
        if not ans:
            st.markdown("""<div class="empty"><div class="empty-ic">🧪</div><div class="empty-t">No answers yet</div><div class="empty-sub">Run the pipeline from the Upload tab first</div></div>""", unsafe_allow_html=True)
        elif not st.session_state.review_queue:
            st.markdown("""<div class="autoemail"><div class="autoemail-ic">✅</div><div><div class="autoemail-t">All items resolved!</div><div class="autoemail-sub">Check the Deliver tab for export, email draft, and Slack notification.</div></div></div>""", unsafe_allow_html=True)
            if not st.session_state.balloons_shown:
                st.balloons()
                st.session_state.balloons_shown = True
        else:
            remaining = len(st.session_state.review_queue)
            total = st.session_state.total_review_items or (
                remaining + sum(1 for a in st.session_state.answers
                                if a.status != "needs_review" and a.status != "pending"))
            done = total - remaining if total > remaining else 0
            pct = int(done / total * 100) if total > 0 else 0

            qids = list(st.session_state.review_queue)
            sel = st.session_state.get("rsel", qids[0] if qids else None)
            if sel not in qids:
                sel = qids[0] if qids else None

            # Render two side-by-side columns inside the navigation dashboard card
            col_nav1, col_nav2 = st.columns([1, 1], gap="medium")
            
            with col_nav1:
                st.markdown(f"""
                <div class="nav-card" style="height:100%">
                  <div class="review-progress-top" style="margin-bottom:12px">
                    <span class="review-progress-lbl" style="font-size:10px;color:var(--text3);font-weight:700;text-transform:uppercase;letter-spacing:.08em">Review Progress</span>
                    <span class="review-progress-val" style="font-size:16px;font-weight:800;color:var(--green)">{done} / {total} approved</span>
                  </div>
                  <div class="review-progress-bar" style="height:6px;background:rgba(255,255,255,.03);border-radius:999px;overflow:hidden;margin-bottom:14px">
                    <div class="review-progress-fill" style="width:{pct}%;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--green),var(--primary-light));box-shadow:0 0 10px rgba(52,211,153,.25);transition:width .4s ease"></div>
                  </div>
                  <div style="display:flex;justify-content:space-between;align-items:center">
                    <span style="font-size:11px;color:var(--text3)">⏳ {remaining} item(s) remaining</span>
                    <span class="chip co" style="font-size:9.5px;padding:2px 8px;font-weight:600;background:rgba(52,211,153,.08);border:1px solid rgba(52,211,153,.15)">{pct}% Complete</span>
                  </div>
                </div>
                """, unsafe_allow_html=True)

            with col_nav2:
                st.markdown('<div class="nav-card" style="height:100%">', unsafe_allow_html=True)
                
                idx = qids.index(sel) if sel in qids else 0
                sel_idx = qids.index(sel) if sel in qids else 0
                
                c2_1, c2_2, c2_3 = st.columns([1, 2, 1])
                with c2_1:
                    prev_disabled = (idx == 0)
                    if st.button("◀ Prev", use_container_width=True, disabled=prev_disabled, key="prev_rev_v2"):
                        st.session_state.rsel = qids[idx - 1]
                        st.rerun()
                with c2_2:
                    st.markdown(f"""
                    <div style="text-align:center;padding:4px 0">
                      <div style="font-size:9px;color:var(--text3);text-transform:uppercase;font-weight:600;letter-spacing:.05em">Viewing Item</div>
                      <div style="font-size:12px;font-weight:700;color:var(--primary-light);margin-top:2px">{sel_idx + 1} of {len(qids)} <span style="font-family:'JetBrains Mono',monospace;color:var(--text3);font-weight:400">({sel})</span></div>
                    </div>
                    """, unsafe_allow_html=True)
                with c2_3:
                    next_disabled = (idx >= len(qids) - 1)
                    if st.button("Next ▶", use_container_width=True, disabled=next_disabled, key="next_rev_v2"):
                        st.session_state.rsel = qids[idx + 1]
                        st.rerun()
                
                st.markdown('<div style="margin-top:12px"></div>', unsafe_allow_html=True)
                sel = st.selectbox(
                    "Navigate to question",
                    options=qids,
                    index=qids.index(sel) if sel in qids else 0,
                    format_func=lambda qid: f"{qid}: {next((a.question_text[:50] for a in st.session_state.answers if a.question_id == qid), '')}...",
                    key="rsel_v2",
                    label_visibility="collapsed",
                )
                
                st.markdown('</div>', unsafe_allow_html=True)

            # Bulk Action Row
            col_bulk1, col_bulk2 = st.columns([1, 1], gap="medium")
            with col_bulk1:
                st.markdown('<div class="btn-approve-all">', unsafe_allow_html=True)
                if st.button("✅ Approve All Remaining", use_container_width=True, key="approve_all"):
                    for a in st.session_state.answers:
                        if a.question_id in st.session_state.review_queue and a.status == "needs_review":
                            a.status = "human_approved"
                    st.session_state.review_queue = []
                    st.session_state.final_status = "completed"
                    st.session_state.pipe_stage = 4
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div style="margin-top:24px"></div>', unsafe_allow_html=True)

            cur = _ans(sel) if sel else (_ans(qids[0]) if qids else None)

            if cur:
                cat = next((q.category for q in st.session_state.questions if q.id == cur.question_id), "general")
                cat_icons = {"technical": "🔧", "certification": "📜", "legal": "⚖️", "data-privacy": "🔐", "general": "📋"}
                cat_icon = cat_icons.get(cat, "📋")

                st.markdown(f"""
                <div class="rpanel">
                  <div class="rpanel-head">
                    <span class="rpanel-id">{cur.question_id}</span>
                    <span class="rpanel-cat qrow-c {cat}">{cat_icon} {cat.replace("-", " ")}</span>
                  </div>
                  <div class="rpanel-q">{cur.question_text}</div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown('<div style="margin-top:14px"></div>', unsafe_allow_html=True)

                # Confidence + Status grid
                pct = int(cur.confidence * 100)
                clr = "#34d399" if cur.confidence >= 0.7 else ("#fbbf24" if cur.confidence >= 0.4 else "#ef4444")
                grd = "linear-gradient(90deg,#059669,#34d399)" if cur.confidence >= 0.7 else (
                    "linear-gradient(90deg,#d97706,#fbbf24)" if cur.confidence >= 0.4 else "linear-gradient(90deg,#dc2626,#ef4444)")

                st.markdown(f"""
                <div class="conf-grid">
                  <div class="conf-card" style="background:rgba(99,102,241,.03);border:1px solid rgba(99,102,241,.08)">
                    <div class="conf-card-top">
                      <span class="conf-card-lbl">Confidence Score</span>
                      <span class="conf-card-val" style="color:{clr}">{pct}%</span>
                    </div>
                    <div class="conf-card-bar"><div class="conf-card-fill" style="width:{pct}%;background:{grd}"></div></div>
                    <div style="font-size:10px;color:var(--text3);margin-top:6px;font-weight:600">
                      {'✅ Above threshold (70%)' if cur.confidence >= 0.7 else '⚠️ Below threshold (70%)'}
                    </div>
                  </div>
                  <div class="conf-card" style="background:{'rgba(52,211,153,.03)' if cur.status == 'auto_approved' or cur.status == 'human_approved' else 'rgba(251,191,36,.03)'};border:1px solid {'rgba(52,211,153,.08)' if cur.status == 'auto_approved' or cur.status == 'human_approved' else 'rgba(251,191,36,.08)'}">
                    <div class="conf-card-top">
                      <span class="conf-card-lbl">Current Status</span>
                      <span class="conf-card-val" style="font-size:15px;color:{'var(--green)' if cur.status == 'auto_approved' or cur.status == 'human_approved' else 'var(--amber)'}">
                        {'✅ Auto-Approved' if cur.status == 'auto_approved' else '⏳ Needs Review' if cur.status == 'needs_review' else '👤 Human-Approved' if cur.status == 'human_approved' else '❌ Rejected'}
                      </span>
                    </div>
                    <div style="font-size:10.5px;color:var(--text3);margin-top:6px;font-weight:500">
                      Evidence: <strong style="color:var(--text2)">{len(cur.evidence)}</strong> source(s) cited
                      · Flags: <strong style="color:var(--text2)">{len(cur.risk_flags)}</strong>
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown('<div style="margin-top:14px"></div>', unsafe_allow_html=True)

                # Risk flags
                if cur.risk_flags:
                    st.markdown("**🚩 Risk Flags**")
                    fh = "".join(
                        f'<div class="flag {_fc(f)}"><span class="flag-icon">{_fi(f)}</span> {f}</div>'
                        for f in cur.risk_flags
                    )
                    st.markdown(f'<div class="flags">{fh}</div>', unsafe_allow_html=True)
                    st.markdown('<div style="margin-top:14px"></div>', unsafe_allow_html=True)

                # Evidence citations
                if cur.evidence:
                    st.markdown("**📄 Source Evidence**")
                    ch = "".join(f'<span class="cite">📄 {e}</span>' for e in cur.evidence)
                    st.markdown(f'<div class="cites">{ch}</div>', unsafe_allow_html=True)
                    st.markdown('<div style="margin-top:14px"></div>', unsafe_allow_html=True)

                # Answer editor
                st.markdown(f'<div class="answer-section"><div class="answer-section-lbl">✏️ Draft Answer</div></div>', unsafe_allow_html=True)
                ed = st.text_area("Answer", value=cur.draft, height=160, label_visibility="collapsed",
                                  key=f"d_{cur.question_id}")

                st.markdown('<div style="margin-top:14px"></div>', unsafe_allow_html=True)

                # Action buttons wrapped in styling classes
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown('<div class="btn-approve">', unsafe_allow_html=True)
                    if st.button("✅ Approve", use_container_width=True, key=f"ap_{cur.question_id}"):
                        _upd(cur.model_copy(update={"draft": ed, "status": "human_approved"}))
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                with c2:
                    st.markdown('<div class="btn-edit">', unsafe_allow_html=True)
                    if st.button("✏️ Edit & Approve", use_container_width=True, key=f"ed_{cur.question_id}"):
                        _upd(cur.model_copy(update={"draft": ed, "status": "human_approved"}))
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                with c3:
                    st.markdown('<div class="btn-reject">', unsafe_allow_html=True)
                    if st.button("❌ Reject", use_container_width=True, key=f"rj_{cur.question_id}"):
                        _upd(cur.model_copy(update={"draft": ed, "status": "rejected"}))
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

    # ── DELIVER TAB ──
    with t_del:
        ans = st.session_state.answers
        if not ans:
            st.markdown("""<div class="empty"><div class="empty-ic">📦</div><div class="empty-t">No deliverables yet</div><div class="empty-sub">Complete the pipeline first</div></div>""", unsafe_allow_html=True)
        elif st.session_state.review_queue:
            n = len(st.session_state.review_queue)
            st.markdown(f"""<div style="background:rgba(251,191,36,.04);border:1px solid rgba(251,191,36,.12);border-radius:10px;padding:20px;text-align:center">
              <div style="font-size:24px;margin-bottom:6px">⏳</div>
              <div style="font-size:14px;font-weight:600;color:var(--amber)">{n} item(s) still need review</div>
              <div style="font-size:11.5px;color:var(--text3);margin-top:3px">Resolve all items in the Review tab before delivery.</div>
            </div>""", unsafe_allow_html=True)
        else:
            s = summarize_run(ans)
            er = send_prospect_email(ans, dry_run=True)
            if er.get("email"):
                st.session_state.email_sent = True
                avg = er.get("avg_confidence", 0)
                st.markdown(f"""<div class="autoemail"><div class="autoemail-ic">✉️</div>
                  <div><div class="autoemail-t">Auto-email ready — {avg:.0%} average confidence</div>
                  <div class="autoemail-sub">The completed questionnaire is ready to be sent to the prospect automatically.</div></div></div>""", unsafe_allow_html=True)

            # Stats dashboard
            st.markdown(f"""<div class="dgrid">
              <div class="dstat" style="border-color:rgba(99,102,241,.08)"><div class="dstat-icon">📊</div><div class="dstat-k">Total Questions</div><div class="dstat-v" style="color:var(--text)">{s.total}</div></div>
              <div class="dstat" style="border-color:rgba(52,211,153,.08)"><div class="dstat-icon">✅</div><div class="dstat-k">Auto-Approved</div><div class="dstat-v" style="color:var(--green)">{s.auto_approved}</div></div>
              <div class="dstat" style="border-color:rgba(14,165,233,.08)"><div class="dstat-icon">👤</div><div class="dstat-k">Human-Approved</div><div class="dstat-v" style="color:var(--blue)">{s.human_approved}</div></div>
              <div class="dstat" style="border-color:rgba(239,68,68,.08)"><div class="dstat-icon">❌</div><div class="dstat-k">Rejected</div><div class="dstat-v" style="color:var(--red)">{s.rejected}</div></div>
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
                cat_icons_2 = {"technical": "🔧", "certification": "📜", "legal": "⚖️", "data-privacy": "🔐", "general": "📋"}
                for cat, cnt in sorted(cat_counts.items()):
                    cat_html += f'<span class="chip ct">{cat_icons_2.get(cat, "📋")} {cat.replace("-", " ")}: {cnt}</span>'
                cat_html += '</div>'
                st.markdown(cat_html, unsafe_allow_html=True)

            # Three-column actions
            aC, bC, cC = st.columns(3)
            with aC:
                st.markdown("""<div class="acard"><div class="acard-head"><div class="acard-ic" style="background:rgba(99,102,241,.08)">📊</div><div><div class="acard-t">Export Workbook</div><div class="acard-sub">Complete .xlsx with all Q&A</div></div></div>""", unsafe_allow_html=True)
                tmp = export_workbook(ans, filename="trustloop_export.xlsx")
                st.download_button("⬇ Download .xlsx", data=io.BytesIO(tmp.read_bytes()),
                                   file_name="trustloop_export.xlsx", type="primary", use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

            with bC:
                em = draft_prospect_email(ans)
                fl, _, rest = em.partition("\n\n")
                subj = fl.replace("Subject: ", "")
                st.markdown(f"""<div class="acard"><div class="acard-head"><div class="acard-ic" style="background:rgba(168,85,247,.08)">✉️</div><div><div class="acard-t">Prospect Email</div><div class="acard-sub">Ready to send</div></div></div>
                <div class="email-mock"><div class="email-bar"><b>Subject:</b> {subj}</div><div class="email-body">{rest}</div></div></div>""", unsafe_allow_html=True)

            with cC:
                sb = build_slack_notification(ans)
                now = time.strftime("%I:%M %p")
                st.markdown(f"""<div class="acard"><div class="acard-head"><div class="acard-ic" style="background:rgba(52,211,153,.08)">💬</div><div><div class="acard-t">Slack Notification</div><div class="acard-sub">#deals channel</div></div></div>
                <div class="slack-mock"><div class="slack-row"><div class="slack-av">🛡️</div><div><div><span class="slack-name">TrustLoop</span><span class="slack-time">{now}</span></div><div class="slack-body">{sb}</div></div></div></div></div>""", unsafe_allow_html=True)

    # ── KB TAB ──
    with t_kb:
        st.markdown("### 📚 Knowledge Base")
        st.markdown("Grounded evidence sources used by the research agent. Every answer cites specific documents from this base.")
        kb = Path("kb")
        if kb.exists():
            items = ""
            for f in sorted(kb.glob("*.md")):
                c = f.read_text()
                title = c.split("\n")[0].replace("# ", "")
                desc_lines = [l.strip() for l in c.split("\n")[1:4] if l.strip() and not l.startswith("#")]
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
                items += f'<div class="kbcard"><div class="kbcard-name">📄 {f.name}</div><div class="kbcard-title">{title}</div><div class="kbcard-desc">{desc}…</div><div class="kbcard-tags">{tags_html}</div></div>'
            st.markdown(f'<div class="kbgrid">{items}</div>', unsafe_allow_html=True)

    # Auto-run pipeline for demo — rerun at the very end of script to allow full render
    if st.session_state.get("auto_run") and st.session_state.pipe_stage < 4:
        time.sleep(0.6)
        st.rerun()

