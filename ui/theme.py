"""Liquisto UI — brand theme CSS injection."""
from __future__ import annotations

# ── Liquisto brand palette (derived from liquisto.com) ───────────────────────
TEAL_900 = "#0B3D3F"   # primary dark — nav, headings
TEAL_700 = "#0F5E5F"   # primary mid — active states
TEAL_500 = "#14807F"   # accent — links, highlights
TEAL_100 = "#E6F3F3"   # tint — light backgrounds
TEAL_50  = "#F4F8F7"   # surface — secondary bg (matches config.toml)
SLATE_900 = "#1A2B2D"  # text primary
SLATE_600 = "#4A5E60"  # text secondary
SLATE_300 = "#B0C4C5"  # borders
WHITE = "#FFFFFF"
SURFACE_WARN = "#FFF8F0"
GREEN_600 = "#16A34A"
AMBER_600 = "#D97706"
RED_600 = "#DC2626"

BRAND_CSS = f"""
<style>
/* ── Sidebar ─────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
    width: 19rem !important;
    min-width: 19rem !important;
    background-color: {TEAL_900} !important;
}}
[data-testid="stSidebar"] > div:first-child {{
    width: 19rem !important;
    background-color: {TEAL_900} !important;
}}
[data-testid="stSidebar"] * {{
    color: {WHITE} !important;
}}
[data-testid="stSidebar"] .stTextInput label,
[data-testid="stSidebar"] .stSelectbox label {{
    color: {SLATE_300} !important;
    font-size: 0.82rem !important;
}}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stSelectbox > div > div {{
    background-color: rgba(255,255,255,0.92) !important;
    border-color: rgba(255,255,255,0.3) !important;
    color: {SLATE_900} !important;
}}
[data-testid="stSidebar"] .stButton > button {{
    background-color: {TEAL_500} !important;
    color: {WHITE} !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: background-color 0.15s ease;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
    background-color: {TEAL_700} !important;
}}
[data-testid="stSidebar"] .stButton > button:disabled {{
    background-color: rgba(255,255,255,0.1) !important;
    color: rgba(255,255,255,0.35) !important;
}}
[data-testid="stSidebar"] .stDownloadButton > button {{
    background-color: transparent !important;
    border: 1px solid rgba(255,255,255,0.25) !important;
    color: {WHITE} !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
}}
[data-testid="stSidebar"] .stDownloadButton > button:hover {{
    background-color: rgba(255,255,255,0.08) !important;
}}
[data-testid="stSidebar"] hr {{
    border-color: rgba(255,255,255,0.12) !important;
}}
[data-testid="stSidebar"] .stCaption p {{
    color: {SLATE_300} !important;
    font-size: 0.72rem !important;
}}

/* ── Logo ────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] img {{
    filter: brightness(0) invert(1) !important;
    opacity: 0.92;
}}

/* ── Main area ───────────────────────────────────────────────────────── */
.stApp {{
    background-color: {WHITE} !important;
}}
.stApp header[data-testid="stHeader"] {{
    background-color: {WHITE} !important;
}}

/* ── Language toggle row ─────────────────────────────────────────────── */
.lang-toggle {{
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.5rem;
    padding: 0.25rem 0;
}}
.lang-toggle span {{
    font-size: 0.78rem;
    color: {SLATE_600};
}}

/* ── Tabs ────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0;
    border-bottom: 2px solid {TEAL_100};
}}
.stTabs [data-baseweb="tab"] {{
    padding: 0.6rem 1.2rem;
    font-weight: 500;
    color: {SLATE_600};
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
}}
.stTabs [data-baseweb="tab"][aria-selected="true"] {{
    color: {TEAL_900} !important;
    border-bottom-color: {TEAL_500} !important;
    font-weight: 700;
}}

/* ── Containers / cards ──────────────────────────────────────────────── */
[data-testid="stExpander"] {{
    border: 1px solid {SLATE_300} !important;
    border-radius: 10px !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[data-testid="stVerticalBlock"] > div.element-container) {{
    border-color: {SLATE_300} !important;
    border-radius: 10px !important;
}}

/* ── Progress bar ────────────────────────────────────────────────────── */
.stProgress > div > div > div {{
    background-color: {TEAL_500} !important;
}}

/* ── Metrics ─────────────────────────────────────────────────────────── */
[data-testid="stMetricValue"] {{
    color: {TEAL_900} !important;
    font-weight: 700 !important;
}}

/* ── Pipeline step cards (live run) ──────────────────────────────────── */
.pipeline-step {{
    border: 1px solid {SLATE_300};
    border-radius: 12px;
    padding: 12px;
    min-height: 100px;
    transition: all 0.2s ease;
}}
.pipeline-step.active {{
    background-color: {TEAL_900};
    border-color: {TEAL_900};
}}
.pipeline-step.active .step-icon,
.pipeline-step.active .step-label,
.pipeline-step.active .step-agent {{
    color: {WHITE};
}}
.pipeline-step.inactive {{
    background-color: {TEAL_50};
}}
.step-icon {{ font-size: 24px; }}
.step-label {{ font-weight: 700; margin-top: 6px; color: {SLATE_900}; font-size: 0.85rem; }}
.step-agent {{ font-size: 0.72rem; color: {SLATE_600}; opacity: 0.85; }}
</style>
"""
