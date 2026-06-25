"""
app.py — CTO ERP entry point.
Run with:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from erp.views import asset, customers, dashboard, machine, operator, site, worklog, workorder

st.set_page_config(
    page_title="IRONLINE ACCESS – Fleet Operations",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---- Global theme & Streamlit chrome removal ----
st.markdown(
    """
    <style>
      /* Remove Streamlit default chrome */
      [data-testid="stHeader"] { display: none !important; }
      [data-testid="stSidebar"] { display: none !important; }
      [data-testid="collapsedControl"] { display: none !important; }
      #MainMenu { visibility: hidden; }
      footer { visibility: hidden; }

      /* Push content below fixed navbar */
      .block-container {
        padding-top: 4.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 1200px !important;
      }

      /* Global font */
      html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
      }

      /* ============================================================
         TOP NAVBAR
         ============================================================ */
      .il-navbar {
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 9999;
        display: flex;
        align-items: stretch;
        height: 58px;
        background: #1c1c2e;
        box-shadow: 0 2px 10px rgba(0,0,0,0.35);
      }
      .il-brand {
        display: flex;
        align-items: center;
        gap: 12px;
        background: #E87722;
        padding: 0 22px;
        min-width: 210px;
        text-decoration: none;
      }
      .il-brand-arrow {
        font-size: 28px;
        font-weight: 900;
        color: #fff;
        line-height: 1;
        transform: scaleX(0.75);
        display: inline-block;
      }
      .il-brand-text {
        display: flex;
        flex-direction: column;
        gap: 1px;
      }
      .il-brand-name {
        font-size: 12px;
        font-weight: 800;
        color: #fff;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        line-height: 1.2;
      }
      .il-brand-sub {
        font-size: 9px;
        color: rgba(255,255,255,0.72);
        letter-spacing: 0.14em;
        text-transform: uppercase;
      }
      .il-nav {
        display: flex;
        align-items: center;
        padding: 0 18px;
        gap: 2px;
        flex: 1;
      }
      .il-nav a {
        color: rgba(255,255,255,0.68);
        font-size: 13px;
        font-weight: 500;
        text-decoration: none;
        padding: 6px 16px;
        border-radius: 4px;
        letter-spacing: 0.03em;
        transition: background 0.15s, color 0.15s;
      }
      .il-nav a:hover {
        color: #fff;
        background: rgba(255,255,255,0.10);
      }
      .il-nav a.active {
        color: #E87722;
        background: rgba(232,119,34,0.14);
        font-weight: 600;
      }

      /* ============================================================
         PAGE HEADER
         ============================================================ */
      .page-eyebrow {
        font-size: 11px;
        font-weight: 700;
        color: #E87722;
        letter-spacing: 0.13em;
        text-transform: uppercase;
        margin-bottom: 4px;
        margin-top: 0;
      }
      .page-title {
        font-size: 28px;
        font-weight: 800;
        color: #111827;
        letter-spacing: -0.01em;
        margin: 0 0 0 0;
        line-height: 1.1;
      }

      /* ============================================================
         METRIC CARDS
         ============================================================ */
      .metric-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        padding: 20px 22px 18px;
        position: relative;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        min-height: 100px;
      }
      .metric-label {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.13em;
        color: #9ca3af;
        text-transform: uppercase;
        margin-bottom: 10px;
      }
      .metric-value {
        font-size: 46px;
        font-weight: 800;
        line-height: 1;
      }
      .metric-icon {
        position: absolute;
        top: 18px;
        right: 18px;
        font-size: 18px;
        opacity: 0.75;
      }

      /* ============================================================
         FILTERS
         ============================================================ */
      .filter-label {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.13em;
        color: #6b7280;
        text-transform: uppercase;
        margin: 0 0 4px 0;
      }

      /* ============================================================
         CTA BUTTON
         ============================================================ */
      .btn-orange {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        background: #E87722;
        color: #fff !important;
        text-decoration: none !important;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        padding: 10px 18px;
        border-radius: 4px;
        white-space: nowrap;
        margin-top: 6px;
      }
      .btn-orange:hover {
        background: #cf6a1a;
      }

      /* Override Streamlit's native buttons to follow brand */
      [data-testid="baseButton-primary"],
      [data-testid="baseButton-secondary"] {
        background-color: #E87722 !important;
        color: #fff !important;
        border: none !important;
        font-weight: 600 !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---- Determine active page from query params ----
page = st.query_params.get("page", "dashboard")

# ---- Inject top navbar ----
def _cls(p: str) -> str:
    return "active" if page == p else ""

st.markdown(
    f"""
    <div class="il-navbar">
      <a class="il-brand" href="?page=dashboard" target="_self">
        <span class="il-brand-arrow">&#8679;</span>
        <div class="il-brand-text">
          <span class="il-brand-name">Ironline Access</span>
          <span class="il-brand-sub">Boomlifft Rental Ops</span>
        </div>
      </a>
      <nav class="il-nav">
        <a href="?page=dashboard"  target="_self" class="{_cls('dashboard')}">Dashboard</a>
        <a href="?page=customers"  target="_self" class="{_cls('customers')}">Customers</a>
        <a href="?page=sites"      target="_self" class="{_cls('sites')}">Sites</a>
        <a href="?page=operators"  target="_self" class="{_cls('operators')}">Operators</a>
        <a href="?page=machines"   target="_self" class="{_cls('machines')}">Machines</a>
        <a href="?page=assets"     target="_self" class="{_cls('assets')}">Assets</a>
        <a href="?page=workorders" target="_self" class="{_cls('workorders')}">Work Orders</a>
        <a href="?page=worklog"    target="_self" class="{_cls('worklog')}">Worklog</a>
        <a href="?page=system"     target="_self" class="{_cls('system')}">System</a>
      </nav>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---- Route to page ----
if page == "dashboard":
    dashboard.render()
elif page == "machines":
    machine.render()
elif page == "customers":
    customers.render()
elif page == "sites":
    site.render()
elif page == "operators":
    operator.render()
elif page == "assets":
    asset.render()
elif page == "workorders":
    workorder.render()
elif page == "worklog":
    worklog.render()
elif page == "system":
    st.markdown(
        """
        <div class="page-eyebrow">// Configuration</div>
        <div class="page-title">System</div>
        """,
        unsafe_allow_html=True,
    )
    st.info("System settings coming soon.")
else:
    dashboard.render()
