"""
app.py — CTO ERP entry point.
Run with:  streamlit run app.py
"""
from __future__ import annotations
import os
import sys

# Ensure the project root is always on sys.path so `import erp` works
# correctly on Streamlit Cloud regardless of working directory.
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from streamlit_cookies_controller import CookieController

from erp import auth
from erp.supabase_client import SupabaseClient
from erp.views import (
    admin,
    asset,
    currentdeployment,
    customerreport,
    customers,
    dashboard,
    deployment,
    fleetstatus,
    fleetutil,
    login,
    machinehistory,
    wlreports,
    workorderreport,
    operatorreport,
    machine,
    operator,
    site,
    worklog,
    worklogreport,
    workorder,
)

st.set_page_config(
    page_title="IRONLINE ACCESS – Fleet Operations",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---- Global theme, design system & Streamlit chrome removal ----
st.markdown(
    """<style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
      @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20,400,0,0');

      /* ══════════════════════════════════════════════════
         DESIGN TOKENS
         ══════════════════════════════════════════════════ */
      :root {
        /* Brand */
        --primary:       #2563EB;
        --primary-hover: #1D4ED8;
        --primary-light: #EFF6FF;
        --primary-ring:  rgba(37,99,235,.20);
        --brand:         #E87722;
        --brand-light:   rgba(232,119,34,.10);

        /* Surfaces */
        --bg:            #F8FAFC;
        --card:          #FFFFFF;
        --border:        #E2EBF0;
        --border-focus:  #93C5FD;

        /* Semantic colours */
        --success:       #16A344;
        --success-bg:    #DCFCE7;
        --warning:       #F59E0B;
        --warning-bg:    #FFFBEB;
        --danger:        #DC2626;
        --danger-bg:     #FEE2E2;
        --error:         #DC2626;
        --error-bg:      #FEE2E2;
        --info:          #0EA5E9;
        --info-bg:       #E0F2FE;

        /* Typography */
        --text-pri:      #1E2938;
        --text-sec:      #6B7280;
        --text-muted:    #9CA3AF;

        /* Layout */
        --sidebar-bg:    #0f172a;
        --sidebar-w:     240px;
        --topbar-h:      58px;
        --radius:        10px;
        --radius-sm:     6px;

        /* Shadows */
        --shadow-xs:     0 1px 2px rgba(0,0,0,.05);
        --shadow-sm:     0 1px 3px rgba(0,0,0,.07), 0 1px 2px rgba(0,0,0,.04);
        --shadow-md:     0 4px 6px -1px rgba(0,0,0,.10), 0 2px 4px -1px rgba(0,0,0,.06);
      }

      /* ── Streamlit chrome removal ── */
      [data-testid="stHeader"],
      [data-testid="stSidebar"],
      [data-testid="collapsedControl"],
      [data-testid="stDecoration"] { display: none !important; }
      #MainMenu { visibility: hidden; }
      footer     { visibility: hidden; }

      /* ── Base ── */
      html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif !important;
        background: var(--bg) !important;
        color: var(--text-pri) !important;
      }

      /* ── Main content area (offset for sidebar + topbar) ── */
      .block-container {
        padding-top:    calc(var(--topbar-h) + 28px) !important;
        padding-left:   calc(var(--sidebar-w) + 28px) !important;
        padding-right:  32px !important;
        padding-bottom: 56px !important;
        max-width:      100% !important;
        background:     var(--bg) !important;
      }

      /* ══════════════════════════════════════════════════
         LEFT SIDEBAR — dark theme
         ══════════════════════════════════════════════════ */
      .il-sidebar {
        position: fixed;
        top: 0; left: 0; bottom: 0;
        width: var(--sidebar-w);
        background: var(--sidebar-bg);
        z-index: 9999;
        display: flex;
        flex-direction: column;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-width: none;
        box-shadow: 2px 0 8px rgba(0,0,0,.18);
      }
      .il-sidebar::-webkit-scrollbar { display: none; }

      /* Brand strip */
      .il-sb-brand {
        display: flex; align-items: center; gap: 11px;
        padding: 0 16px;
        height: var(--topbar-h);
        border-bottom: 1px solid rgba(255,255,255,.07);
        flex-shrink: 0;
        text-decoration: none !important;
      }
      .il-sb-logo {
        width: 34px; height: 34px;
        background: var(--primary);
        border-radius: 8px;
        display: flex; align-items: center; justify-content: center;
        font-size: 12px; font-weight: 800;
        color: #fff; letter-spacing: .04em;
        flex-shrink: 0;
      }
      .il-sb-brand-name {
        font-size: 13px; font-weight: 700;
        color: #ffffff; letter-spacing: .02em; line-height: 1.3;
      }
      .il-sb-brand-sub {
        font-size: 9px; color: rgba(255,255,255,.40);
        letter-spacing: .12em; text-transform: uppercase; margin-top: 1px;
      }

      /* Nav */
      .il-sb-nav { padding: 8px 0 24px; flex: 1; }

      .il-sb-section {
        padding: 16px 20px 4px;
        font-size: 9px; font-weight: 700;
        letter-spacing: .14em; text-transform: uppercase;
        color: rgba(255,255,255,.32); user-select: none;
      }
      .il-sb-divider {
        height: 1px; background: rgba(255,255,255,.07);
        margin: 6px 16px;
      }

      /* Nav items */
      .il-sb-item,
      .il-sb-item:link,
      .il-sb-item:visited {
        display: flex; align-items: center; gap: 10px;
        padding: 9px 14px 9px 16px;
        margin: 1px 8px;
        border-radius: 8px;
        text-decoration: none !important;
        font-size: 13px; font-weight: 600;
        color: #ffffff !important;
        transition: background .14s, color .14s;
        position: relative;
      }
      .il-sb-item:hover,
      .il-sb-item:focus {
        background: rgba(255,255,255,.10);
        color: #ffffff !important;
        text-decoration: none !important;
      }
      .il-sb-item.active,
      .il-sb-item.active:link,
      .il-sb-item.active:visited,
      .il-sb-item.active:hover {
        background: var(--primary) !important;
        color: #ffffff !important;
        font-weight: 700;
        box-shadow: 0 2px 8px rgba(37,99,235,.40);
      }
      /* Left indicator bar on active item */
      .il-sb-item.active::before {
        content: '';
        position: absolute;
        left: -8px;
        top: 50%; transform: translateY(-50%);
        width: 3px; height: 60%;
        background: #ffffff;
        border-radius: 0 3px 3px 0;
      }

      /* ── User profile at bottom ── */
      .il-sb-user {
        display: flex; align-items: center; gap: 10px;
        padding: 12px 14px;
        border-top: 1px solid rgba(255,255,255,.07);
        cursor: pointer;
        transition: background .14s;
        flex-shrink: 0;
        text-decoration: none !important;
      }
      .il-sb-user:hover { background: rgba(255,255,255,.07); }
      .il-sb-user-avatar {
        width: 34px; height: 34px; border-radius: 50%;
        background: var(--primary);
        display: flex; align-items: center; justify-content: center;
        font-size: 11px; font-weight: 800; color: #fff;
        flex-shrink: 0; letter-spacing: .03em;
      }
      .il-sb-user-info { flex: 1; min-width: 0; }
      .il-sb-user-name {
        font-size: 12px; font-weight: 700; color: #fff;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        line-height: 1.3;
      }
      .il-sb-user-role {
        font-size: 9px; color: rgba(255,255,255,.40);
        text-transform: uppercase; letter-spacing: .10em; margin-top: 1px;
      }
      .il-sb-user-arrow {
        font-size: 16px !important; color: rgba(255,255,255,.30); flex-shrink: 0;
      }

      /* Material Symbols base class */
      .msr {
        font-family: 'Material Symbols Rounded';
        font-style: normal; font-weight: normal; font-size: inherit;
        line-height: 1; display: inline-block; vertical-align: middle;
        -webkit-font-feature-settings: 'liga';
        font-feature-settings: 'liga';
        -webkit-font-smoothing: antialiased;
      }
      .il-sb-item .msr {
        font-size: 18px !important; flex-shrink: 0;
        opacity: .85;
        transition: opacity .14s;
      }
      .il-sb-item:hover .msr { opacity: 1; }
      .il-sb-item.active .msr { opacity: 1; color: #fff; }
      .il-sb-label { white-space: nowrap; }

      /* ══════════════════════════════════════════════════
         TOPBAR
         ══════════════════════════════════════════════════ */
      .il-topbar {
        position: fixed;
        top: 0; left: var(--sidebar-w); right: 0;
        height: var(--topbar-h);
        background: #fff;
        border-bottom: 1px solid var(--border);
        display: flex; align-items: center;
        padding: 0 24px; gap: 12px;
        z-index: 9998;
        box-shadow: var(--shadow-xs);
      }
      .il-breadcrumb {
        display: flex; align-items: center; gap: 6px;
        flex: 1; min-width: 0;
      }
      .il-bc-sep     { color: var(--text-muted); font-size: 13px; }
      .il-bc-section { font-size: 12px; color: var(--text-sec); font-weight: 500; }
      .il-bc-current {
        font-size: 14px; font-weight: 700; color: var(--text-pri);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .il-topbar-right {
        display: flex; align-items: center; gap: 8px; flex-shrink: 0;
      }
      .il-search-box {
        display: flex; align-items: center; gap: 8px;
        background: var(--bg); border: 1px solid var(--border);
        border-radius: var(--radius-sm); padding: 7px 14px;
        width: 200px; cursor: text;
        color: var(--text-muted); font-size: 13px;
        transition: border-color .14s;
      }
      .il-search-box:hover { border-color: #C4CEDB; }
      .il-notif-btn {
        width: 36px; height: 36px;
        display: flex; align-items: center; justify-content: center;
        border-radius: var(--radius-sm); cursor: pointer;
        transition: background .14s;
        color: var(--text-sec);
      }
      .il-notif-btn:hover { background: var(--bg); }
      .il-user-area {
        display: flex; align-items: center; gap: 8px;
        padding: 5px 10px 5px 6px;
        border-radius: var(--radius-sm); cursor: pointer;
        border: 1px solid var(--border);
        transition: background .14s, border-color .14s;
      }
      .il-user-area:hover { background: var(--bg); border-color: #C4CEDB; }
      .il-avatar {
        width: 30px; height: 30px; border-radius: 50%;
        background: var(--primary);
        display: flex; align-items: center; justify-content: center;
        font-size: 11px; font-weight: 700; color: #fff; flex-shrink: 0;
      }
      .il-user-name-tb {
        font-size: 12px; font-weight: 600; color: var(--text-pri);
        max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      }
      .il-signout-link {
        font-size: 11px; color: var(--text-muted);
        text-decoration: none !important;
        padding: 3px 8px; border-radius: 4px;
        border: 1px solid var(--border);
        transition: color .14s, background .14s, border-color .14s;
        white-space: nowrap; margin-left: 2px;
      }
      .il-signout-link:hover {
        color: var(--danger); border-color: var(--danger); background: var(--danger-bg);
      }

      /* ══════════════════════════════════════════════════
         PAGE HEADER
         ══════════════════════════════════════════════════ */
      .page-eyebrow {
        font-size: 11px; font-weight: 700; color: var(--brand);
        letter-spacing: .13em; text-transform: uppercase;
        margin-bottom: 4px; margin-top: 0;
      }
      .page-title {
        font-size: 26px; font-weight: 800; color: var(--text-pri);
        letter-spacing: -.02em; margin: 0; line-height: 1.15;
      }

      /* ══════════════════════════════════════════════════
         STATUS BADGES
         ══════════════════════════════════════════════════ */
      .badge {
        display: inline-flex; align-items: center;
        padding: 3px 10px; border-radius: 20px;
        font-size: 10px; font-weight: 700;
        letter-spacing: .04em; white-space: nowrap; line-height: 1.6;
      }
      .badge-available    { background: #DCFCE7; color: #166534; }
      .badge-on-rent      { background: #DBEAFE; color: #1E40AF; }
      .badge-reserved     { background: #FEF3C7; color: #92400E; }
      .badge-breakdown    { background: #FEE2E2; color: #991B1B; }
      .badge-in-transit   { background: #FFEDD5; color: #C2410C; }
      .badge-mobilizing   { background: #FFEDD5; color: #C2410C; }
      .badge-demobilizing { background: #EDE9FE; color: #6D28D9; }
      .badge-sold         { background: #F3F4F6; color: #6B7280; }
      .badge-pending      { background: #FEF3C7; color: #92400E; }
      .badge-completed    { background: #DCFCE7; color: #166534; }
      .badge-draft        { background: #F1F5F9; color: #64748B; }
      .badge-active       { background: #DBEAFE; color: #1E40AF; }
      .badge-approved     { background: #DCFCE7; color: #166534; }
      .badge-overdue      { background: #FEE2E2; color: #991B1B; }
      .badge-running      { background: #DBEAFE; color: #1E40AF; }
      .badge-closed       { background: #F1F5F9; color: #64748B; }

      /* ══════════════════════════════════════════════════
         METRIC / KPI CARDS
         ══════════════════════════════════════════════════ */
      .metric-card {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 20px 22px 18px;
        position: relative;
        box-shadow: var(--shadow-sm);
        min-height: 100px;
        transition: box-shadow .2s, border-color .2s;
      }
      .metric-card:hover {
        box-shadow: var(--shadow-md);
        border-color: #C4CEDB;
      }
      .metric-label {
        font-size: 10px; font-weight: 700; letter-spacing: .13em;
        color: var(--text-muted); text-transform: uppercase; margin-bottom: 10px;
      }
      .metric-value  { font-size: 40px; font-weight: 800; line-height: 1; color: var(--text-pri); }
      .metric-icon   { position: absolute; top: 18px; right: 18px; font-size: 20px; opacity: .45; }
      .metric-delta  {
        font-size: 11px; font-weight: 600; margin-top: 6px;
        display: flex; align-items: center; gap: 3px;
      }
      .metric-delta.up   { color: var(--success); }
      .metric-delta.down { color: var(--danger); }

      /* KPI strip (compact row) */
      .kpi-strip {
        display: flex; gap: 16px; flex-wrap: wrap;
        padding: 14px 16px;
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow-xs);
        margin-bottom: 20px;
      }
      .kpi-strip-item { display: flex; flex-direction: column; gap: 2px; min-width: 80px; }
      .kpi-strip-label {
        font-size: 9px; font-weight: 700; letter-spacing: .12em;
        text-transform: uppercase; color: var(--text-muted);
      }
      .kpi-strip-value { font-size: 22px; font-weight: 800; color: var(--text-pri); line-height: 1.1; }
      .kpi-strip-divider { width: 1px; background: var(--border); margin: 2px 0; align-self: stretch; }

      /* ══════════════════════════════════════════════════
         SECTION DIVIDER
         ══════════════════════════════════════════════════ */
      .section-hdr {
        display: flex; align-items: center; gap: 12px;
        margin: 24px 0 12px;
      }
      .section-hdr-line {
        flex: 1; height: 1px; background: var(--border);
      }
      .section-hdr-text {
        font-size: 10px; font-weight: 700; letter-spacing: .14em;
        text-transform: uppercase; color: var(--text-muted);
        white-space: nowrap;
      }

      /* ══════════════════════════════════════════════════
         FILTERS
         ══════════════════════════════════════════════════ */
      .filter-label {
        font-size: 10px; font-weight: 700; letter-spacing: .13em;
        color: var(--text-sec); text-transform: uppercase; margin: 0 0 4px 0;
      }
      .filter-bar {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 14px 16px 8px;
        margin-bottom: 20px;
        box-shadow: var(--shadow-xs);
      }

      /* ══════════════════════════════════════════════════
         BUTTONS (utility HTML classes)
         ══════════════════════════════════════════════════ */
      .btn {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 8px 16px; border-radius: var(--radius-sm);
        font-size: 12px; font-weight: 600; letter-spacing: .03em;
        cursor: pointer; transition: background .14s, box-shadow .14s;
        white-space: nowrap; text-decoration: none !important; border: none;
        box-shadow: var(--shadow-xs);
      }
      .btn-primary  { background: var(--primary);  color: #fff !important; }
      .btn-primary:hover  { background: var(--primary-hover); box-shadow: var(--shadow-sm); }
      .btn-success  { background: var(--success);  color: #fff !important; }
      .btn-success:hover  { background: #138a38; }
      .btn-danger   { background: var(--danger);   color: #fff !important; }
      .btn-danger:hover   { background: #b91c1c; }
      .btn-secondary {
        background: #fff; color: var(--text-pri) !important;
        border: 1px solid var(--border) !important; box-shadow: none;
      }
      .btn-secondary:hover { background: var(--bg); border-color: #C4CEDB !important; }
      /* Legacy alias */
      .btn-orange {
        display: inline-flex; align-items: center; gap: 5px;
        background: var(--primary); color: #fff !important;
        text-decoration: none !important;
        font-size: 12px; font-weight: 700;
        letter-spacing: .06em; text-transform: uppercase;
        padding: 9px 18px; border-radius: var(--radius-sm);
        white-space: nowrap; margin-top: 6px;
        transition: background .14s, box-shadow .14s;
        box-shadow: var(--shadow-xs);
      }
      .btn-orange:hover { background: var(--primary-hover); box-shadow: var(--shadow-sm); }

      /* ══════════════════════════════════════════════════
         STREAMLIT NATIVE WIDGET OVERRIDES
         ══════════════════════════════════════════════════ */
      [data-testid="baseButton-primary"],
      [data-testid="baseButton-secondary"] {
        background-color: var(--primary) !important;
        color: #fff !important; border: none !important;
        font-weight: 600 !important;
        border-radius: var(--radius-sm) !important;
        transition: background-color .14s !important;
      }
      [data-testid="baseButton-primary"]:hover,
      [data-testid="baseButton-secondary"]:hover {
        background-color: var(--primary-hover) !important;
      }

      /* Selectbox / text inputs */
      [data-testid="stSelectbox"] > div > div,
      [data-testid="stTextInput"] > div > div > input,
      [data-testid="stNumberInput"] > div > div > input,
      [data-testid="stDateInput"]  > div > div > input {
        border-radius: var(--radius-sm) !important;
        border-color: var(--border) !important;
        font-size: 13px !important;
        color: var(--text-pri) !important;
      }
      [data-testid="stSelectbox"] > div > div:focus-within,
      [data-testid="stTextInput"] > div > div > input:focus,
      [data-testid="stNumberInput"] > div > div > input:focus {
        border-color: var(--border-focus) !important;
        box-shadow: 0 0 0 3px var(--primary-ring) !important;
      }

      /* Dataframe / table */
      [data-testid="stDataFrame"] {
        border-radius: var(--radius) !important;
        border: 1px solid var(--border) !important;
        overflow: hidden !important;
        box-shadow: var(--shadow-sm) !important;
      }
      [data-testid="stDataFrame"] > div {
        border-radius: var(--radius) !important;
      }

      /* Tabs */
      .stTabs [data-baseweb="tab-list"] {
        gap: 2px !important;
        border-bottom: 2px solid var(--border) !important;
        background: transparent !important;
        padding-bottom: 0 !important;
      }
      .stTabs [data-baseweb="tab"] {
        border-radius: var(--radius-sm) var(--radius-sm) 0 0 !important;
        font-size: 13px !important; font-weight: 500 !important;
        color: var(--text-sec) !important;
        padding: 8px 16px !important;
        background: transparent !important;
      }
      .stTabs [aria-selected="true"] {
        color: var(--primary) !important; font-weight: 700 !important;
        border-bottom: 2px solid var(--primary) !important;
      }
      .stTabs [data-baseweb="tab-panel"] { padding-top: 16px !important; }

      /* Native st.metric */
      [data-testid="stMetric"] {
        background: var(--card) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
        padding: 16px 20px !important;
        box-shadow: var(--shadow-sm) !important;
        transition: box-shadow .2s !important;
      }
      [data-testid="stMetric"]:hover { box-shadow: var(--shadow-md) !important; }

      /* Metric label & value colours */
      [data-testid="stMetricLabel"]  { color: var(--text-muted) !important; font-size: 11px !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: .1em !important; }
      [data-testid="stMetricValue"]  { color: var(--text-pri) !important; font-weight: 800 !important; }
      [data-testid="stMetricDelta"]  { font-size: 12px !important; font-weight: 600 !important; }

      /* Alert boxes */
      [data-testid="stAlert"]  { border-radius: var(--radius-sm) !important; font-size: 13px !important; }

      /* Download button */
      [data-testid="stDownloadButton"] button {
        background: transparent !important;
        border: 1px solid var(--border) !important;
        color: var(--text-sec) !important;
        border-radius: var(--radius-sm) !important;
        font-size: 12px !important; font-weight: 500 !important;
        transition: all .14s !important;
      }
      [data-testid="stDownloadButton"] button:hover {
        border-color: var(--primary) !important;
        color: var(--primary) !important;
        background: var(--primary-light) !important;
      }

      /* Expander */
      [data-testid="stExpander"] {
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-sm) !important;
        overflow: hidden !important;
      }
      [data-testid="stExpander"] summary {
        font-size: 13px !important; font-weight: 600 !important;
        color: var(--text-pri) !important;
        background: var(--card) !important;
        padding: 10px 14px !important;
      }

      /* Toast / success messages */
      [data-testid="stToast"] {
        border-radius: var(--radius-sm) !important;
        font-size: 13px !important;
        box-shadow: var(--shadow-md) !important;
      }

      /* Scrollbar */
      ::-webkit-scrollbar { width: 5px; height: 5px; }
      ::-webkit-scrollbar-track { background: transparent; }
      ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 10px; }
      ::-webkit-scrollbar-thumb:hover { background: #94A3B8; }

      /* ══════════════════════════════════════════════════
         RESPONSIVE — hide sidebar on small screens
         ══════════════════════════════════════════════════ */
      @media (max-width: 768px) {
        .il-sidebar { transform: translateX(-100%); }
        .il-topbar  { left: 0 !important; }
        .block-container {
          padding-left: 16px !important;
          padding-right: 16px !important;
        }
      }
    </style>""",
    unsafe_allow_html=True,
)

# ============================================================
# COOKIE-BASED SESSION PERSISTENCE
# Restores login state after full page reloads (navbar clicks).
# ============================================================
_cc = CookieController()

page = st.query_params.get("page", "dashboard")

# Handle logout BEFORE cookie restoration so cleared cookies
# don't immediately re-log the user back in.
if page == "logout":
    # Invalidate tokens server-side first so stale cookies can't restore
    # the session even if the browser delays removing them.
    try:
        _sb_lo = SupabaseClient()
        _sb_lo.client.auth.sign_out()
    except Exception:
        pass
    _all = _cc.getAll() or {}
    if "il_at" in _all:
        _cc.remove("il_at")
    if "il_rt" in _all:
        _cc.remove("il_rt")
    for _k in list(st.session_state.keys()):
        del st.session_state[_k]
    # Keep these flags so the next render skips cookie restoration and
    # goes straight to the login page instead of trying set_session().
    st.session_state["_cc_synced"] = True
    st.session_state["_logging_out"] = True
    st.query_params["page"] = "dashboard"
    st.rerun()

# Restore session from cookies when session state is empty.
# CookieController can return None OR {} on the first render before it has
# fully synced with the browser.  We always wait one extra render cycle
# (via the _cc_synced flag) before concluding no session exists, so the
# login page never flashes during normal navigation.
if not auth.is_logged_in():
    _all_cookies = _cc.getAll()

    if not st.session_state.get("_cc_synced"):
        # First render of this session — always wait one cycle regardless of
        # what getAll() returned, to let the component finish syncing.
        st.session_state["_cc_synced"] = True
        st.stop()

    # Skip cookie restoration if we just signed out — the browser may not
    # have deleted the cookies yet and the tokens are already invalidated.
    if not st.session_state.get("_logging_out"):
        _at = (_all_cookies or {}).get("il_at")
        _rt = (_all_cookies or {}).get("il_rt")
        if _at and _rt:
            try:
                _sb   = SupabaseClient()
                _resp = _sb.client.auth.set_session(_at, _rt)
                if _resp and _resp.user:
                    _profile = _sb.get_user_profile(str(_resp.user.id))
                    if _profile and _profile.get("is_active", True):
                        st.session_state["user"]    = _resp.user
                        st.session_state["profile"] = _profile
                        st.rerun()
            except Exception:
                _all2 = _cc.getAll() or {}
                if "il_at" in _all2:
                    _cc.remove("il_at")
                if "il_rt" in _all2:
                    _cc.remove("il_rt")

# Show login page if still not authenticated
if not auth.is_logged_in():
    login.render()
    st.stop()

# Save tokens to cookies after a fresh login
if "_new_tokens" in st.session_state:
    _tok = st.session_state.pop("_new_tokens")
    if _tok.get("at"):
        _cc.set("il_at", _tok["at"], max_age=86400 * 7)   # 7 days
    if _tok.get("rt"):
        _cc.set("il_rt", _tok["rt"], max_age=86400 * 30)  # 30 days

# ============================================================
# SIDEBAR + TOPBAR
# ============================================================
_profile   = auth.current_profile()
_user_name = _profile.get("full_name") or _profile.get("email") or "User"

_SIDEBAR_ITEMS = [
    # key, Material Symbol icon name, display label, section
    ("dashboard",      "space_dashboard",        "Dashboard",    "OPERATIONS"),
    ("customers",      "groups",                  "Customers",    "OPERATIONS"),
    ("sites",          "location_on",             "Sites",        "OPERATIONS"),
    ("operators",      "engineering",             "Operators",    "OPERATIONS"),
    ("machines",       "precision_manufacturing", "Machines",     "OPERATIONS"),
    ("assets",         "inventory_2",             "Assets",       "OPERATIONS"),
    ("workorders",     "assignment",              "Work Orders",  "OPERATIONS"),
    ("deployments",    "local_shipping",          "Deployments",  "OPERATIONS"),
    ("worklog",        "edit_note",               "Worklog",      "OPERATIONS"),
    ("currentdep",     "pin_drop",                "Active Dep",   "REPORTS"),
    ("fleetstatus",    "fact_check",              "Fleet Status", "REPORTS"),
    ("fleetutil",      "bar_chart",               "Fleet Util",   "REPORTS"),
    ("machinehistory", "history",                 "Mach History", "REPORTS"),
    ("wlreport",       "description",             "WL Report",    "REPORTS"),
    ("woreport",       "receipt_long",            "WO Report",    "REPORTS"),
    ("wlreports",      "pending_actions",         "WL Status",    "REPORTS"),
    ("custreport",     "person_search",           "Cust Report",  "REPORTS"),
    ("opreport",       "badge",                   "Op Report",    "REPORTS"),
    ("system",         "settings",                "System",       "CONFIG"),
]

_PAGE_LABELS = {key: label for key, _, label, _ in _SIDEBAR_ITEMS}
_PAGE_LABELS["admin"] = "Admin"

_PAGE_SECTION = {key: sec for key, _, _, sec in _SIDEBAR_ITEMS}
_PAGE_SECTION["admin"] = "ADMIN"


def _build_sidebar() -> str:
    last_section = None
    items_html: list[str] = []
    for key, icon, label, section in _SIDEBAR_ITEMS:
        if not auth.has_page_access(key):
            continue
        # Add a subtle divider between sections (no text label — cleaner look)
        if section != last_section:
            if last_section is not None:
                items_html.append("<div class='il-sb-divider'></div>")
            last_section = section
        active_cls = " active" if page == key else ""
        items_html.append(
            f"<a href='?page={key}' target='_self' class='il-sb-item{active_cls}'>"
            f"<span class='msr'>{icon}</span>"
            f"<span class='il-sb-label'>{label}</span>"
            f"</a>"
        )
    if auth.is_admin():
        items_html.append("<div class='il-sb-divider'></div>")
        active_cls = " active" if page == "admin" else ""
        items_html.append(
            f"<a href='?page=admin' target='_self' class='il-sb-item{active_cls}'>"
            f"<span class='msr'>admin_panel_settings</span>"
            f"<span class='il-sb-label'>Admin</span>"
            f"</a>"
        )

    # User profile panel at the bottom
    _initials   = (_user_name or "U")[:2].upper()
    _role_label = "Admin" if auth.is_admin() else (_profile.get("role") or "User")
    _user_panel = (
        f"<a href='?page=system' target='_self' class='il-sb-user'>"
        f"  <div class='il-sb-user-avatar'>{_initials}</div>"
        f"  <div class='il-sb-user-info'>"
        f"    <div class='il-sb-user-name'>{_user_name}</div>"
        f"    <div class='il-sb-user-role'>{_role_label}</div>"
        f"  </div>"
        f"  <span class='msr il-sb-user-arrow'>chevron_right</span>"
        f"</a>"
    )

    return (
        "<div class='il-sidebar'>"
        "  <a href='?page=dashboard' target='_self' class='il-sb-brand'>"
        "    <div class='il-sb-logo'>IA</div>"
        "    <div>"
        "      <div class='il-sb-brand-name'>Ironline Access</div>"
        "      <div class='il-sb-brand-sub'>Fleet Operations</div>"
        "    </div>"
        "  </a>"
        f"  <nav class='il-sb-nav'>{''.join(items_html)}</nav>"
        f"  {_user_panel}"
        "</div>"
    )


def _build_topbar() -> str:
    section   = _PAGE_SECTION.get(page, "OPERATIONS").title()
    pg_label  = _PAGE_LABELS.get(page, "Dashboard")
    initials  = (_user_name or "U")[:2].upper()
    return (
        "<div class='il-topbar'>"
        "  <div class='il-breadcrumb'>"
        "    <span class='msr' style='font-size:15px;color:#9CA3AF;'>home</span>"
        "    <span class='il-bc-sep'>/</span>"
        f"   <span class='il-bc-section'>{section}</span>"
        "    <span class='il-bc-sep'>/</span>"
        f"   <span class='il-bc-current'>{pg_label}</span>"
        "  </div>"
        "  <div class='il-topbar-right'>"
        "    <div class='il-search-box'>"
        "      <span class='msr' style='font-size:16px;'>search</span>"
        "      <span>Search...</span>"
        "    </div>"
        "    <div class='il-notif-btn'>"
        "      <span class='msr' style='font-size:20px;'>notifications</span>"
        "    </div>"
        "    <div class='il-user-area'>"
        f"     <div class='il-avatar'>{initials}</div>"
        f"     <span class='il-user-name-tb'>{_user_name}</span>"
        "      <a href='?page=logout' target='_self' class='il-signout-link'>Sign out</a>"
        "    </div>"
        "  </div>"
        "</div>"
    )


st.markdown(_build_sidebar(), unsafe_allow_html=True)
st.markdown(_build_topbar(),  unsafe_allow_html=True)

# ============================================================
# PAGE ROUTING
# ============================================================

def _access_denied() -> None:
    st.warning("You don't have access to this page.", icon="🔒")


if page == "dashboard":
    if auth.has_page_access("dashboard"):
        dashboard.render()
    else:
        _access_denied()

elif page == "machines":
    if auth.has_page_access("machines"):
        machine.render()
    else:
        _access_denied()

elif page == "customers":
    if auth.has_page_access("customers"):
        customers.render()
    else:
        _access_denied()

elif page == "sites":
    if auth.has_page_access("sites"):
        site.render()
    else:
        _access_denied()

elif page == "operators":
    if auth.has_page_access("operators"):
        operator.render()
    else:
        _access_denied()

elif page == "assets":
    if auth.has_page_access("assets"):
        asset.render()
    else:
        _access_denied()

elif page == "workorders":
    if auth.has_page_access("workorders"):
        workorder.render()
    else:
        _access_denied()

elif page == "deployments":
    if auth.has_page_access("deployments"):
        deployment.render()
    else:
        _access_denied()

elif page == "worklog":
    if auth.has_page_access("worklog"):
        worklog.render()
    else:
        _access_denied()

elif page == "wlreport":
    if auth.has_page_access("wlreport"):
        worklogreport.render()
    else:
        _access_denied()

elif page == "currentdep":
    if auth.has_page_access("currentdep"):
        currentdeployment.render()
    else:
        _access_denied()

elif page == "fleetstatus":
    if auth.has_page_access("fleetstatus"):
        fleetstatus.render()
    else:
        _access_denied()

elif page == "fleetutil":
    if auth.has_page_access("fleetutil"):
        fleetutil.render()
    else:
        _access_denied()

elif page == "machinehistory":
    if auth.has_page_access("machinehistory"):
        machinehistory.render()
    else:
        _access_denied()

elif page == "woreport":
    if auth.has_page_access("woreport"):
        workorderreport.render()
    else:
        _access_denied()

elif page == "wlreports":
    if auth.has_page_access("wlreports"):
        wlreports.render()
    else:
        _access_denied()

elif page == "custreport":
    if auth.has_page_access("custreport"):
        customerreport.render()
    else:
        _access_denied()

elif page == "opreport":
    if auth.has_page_access("opreport"):
        operatorreport.render()
    else:
        _access_denied()

elif page == "system":
    if auth.has_page_access("system"):
        st.markdown(
            """
            <div class="page-eyebrow">// Configuration</div>
            <div class="page-title">System</div>
            """,
            unsafe_allow_html=True,
        )
        st.info("System settings coming soon.")
    else:
        _access_denied()

elif page == "admin":
    if auth.is_admin():
        admin.render()
    else:
        _access_denied()

else:
    # Unknown page key — fall through to dashboard if accessible
    if auth.has_page_access("dashboard"):
        dashboard.render()
    else:
        _access_denied()
