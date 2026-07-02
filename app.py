"""
app.py — CTO ERP entry point.
Run with:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st
from streamlit_cookies_controller import CookieController

from erp import auth
from erp.supabase_client import SupabaseClient
from erp.views import (
    admin,
    asset,
    customers,
    dashboard,
    deployment,
    login,
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
        overflow-x: auto;
      }
      .il-nav a {
        color: rgba(255,255,255,0.68);
        font-size: 13px;
        font-weight: 500;
        text-decoration: none;
        padding: 6px 14px;
        border-radius: 4px;
        letter-spacing: 0.03em;
        transition: background 0.15s, color 0.15s;
        white-space: nowrap;
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
      /* Admin link gets a subtle accent */
      .il-nav a.admin-nav-link {
        color: rgba(232,119,34,0.80);
      }
      .il-nav a.admin-nav-link:hover {
        color: #E87722;
        background: rgba(232,119,34,0.10);
      }
      .il-nav a.admin-nav-link.active {
        color: #E87722;
        background: rgba(232,119,34,0.18);
      }
      /* Right-side user area */
      .il-nav-right {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 0 18px;
        flex-shrink: 0;
        border-left: 1px solid rgba(255,255,255,0.10);
      }
      .il-user-name {
        font-size: 12px;
        color: rgba(255,255,255,0.50);
        font-weight: 500;
        white-space: nowrap;
        max-width: 160px;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .il-signout {
        color: rgba(255,255,255,0.65);
        font-size: 12px;
        font-weight: 500;
        text-decoration: none;
        padding: 5px 12px;
        border-radius: 4px;
        border: 1px solid rgba(255,255,255,0.18);
        letter-spacing: 0.04em;
        transition: background 0.15s, color 0.15s, border-color 0.15s;
        white-space: nowrap;
      }
      .il-signout:hover {
        color: #fff;
        background: rgba(255,255,255,0.10);
        border-color: rgba(255,255,255,0.35);
      }
      /* Nav section label */
      .il-nav-sep {
        color: rgba(255,255,255,0.18);
        padding: 0 6px;
        font-size: 18px;
        line-height: 1;
        align-self: center;
        flex-shrink: 0;
      }
      .il-nav-section {
        color: rgba(255,255,255,0.35);
        font-size: 9px;
        font-weight: 700;
        letter-spacing: .12em;
        text-transform: uppercase;
        padding: 0 2px 0 4px;
        align-self: center;
        flex-shrink: 0;
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

# ============================================================
# COOKIE-BASED SESSION PERSISTENCE
# Restores login state after full page reloads (navbar clicks).
# ============================================================
_cc = CookieController()

page = st.query_params.get("page", "dashboard")

# Handle logout BEFORE cookie restoration so cleared cookies
# don't immediately re-log the user back in.
if page == "logout":
    _all = _cc.getAll() or {}
    if "il_at" in _all:
        _cc.remove("il_at")
    if "il_rt" in _all:
        _cc.remove("il_rt")
    for _k in list(st.session_state.keys()):
        del st.session_state[_k]
    st.query_params["page"] = "dashboard"
    st.rerun()

# Restore session from cookies when session state is empty.
# CookieController takes one render cycle to load — getAll() returns None
# until the component has initialised.  We stop (without showing the login
# page) so the component can finish loading and trigger an automatic rerun.
if not auth.is_logged_in():
    _all_cookies = _cc.getAll()
    if _all_cookies is None:
        # Component not ready yet — show nothing and wait for its rerun.
        st.stop()

    _at = (_all_cookies or {}).get("il_at")
    _rt = (_all_cookies or {}).get("il_rt")
    if _at and _rt:
        try:
            _sb  = SupabaseClient()
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
# DYNAMIC NAVBAR
# ============================================================
_profile = auth.current_profile()
_user_name = _profile.get("full_name") or _profile.get("email") or "User"

# Pages in display order with an optional section divider.
# Each entry is either ("key", "label") or the string "REPORTS_SEP"
# (which renders the divider + "Reports" label).
_NAV_STRUCTURE = [
    ("dashboard",   "Dashboard"),
    ("customers",   "Customers"),
    ("sites",       "Sites"),
    ("operators",   "Operators"),
    ("machines",    "Machines"),
    ("assets",      "Assets"),
    ("workorders",  "Work Orders"),
    ("deployments", "Deployments"),
    ("worklog",     "Worklog"),
    "REPORTS_SEP",
    ("wlreport",    "Worklog Report"),
    ("system",      "System"),
]


def _cls(p: str) -> str:
    return "active" if page == p else ""


def _build_nav_items() -> str:
    parts: list[str] = []
    sep_rendered = False
    for item in _NAV_STRUCTURE:
        if item == "REPORTS_SEP":
            sep_rendered = True
            continue
        key, label = item  # type: ignore[misc]
        if not auth.has_page_access(key):
            continue
        if sep_rendered:
            parts.append('<span class="il-nav-sep">|</span>')
            parts.append('<span class="il-nav-section">Reports</span>')
            sep_rendered = False
        parts.append(
            f'<a href="?page={key}" target="_self" class="{_cls(key)}">{label}</a>'
        )
    if auth.is_admin():
        parts.append(
            f'<a href="?page=admin" target="_self" '
            f'class="admin-nav-link {_cls("admin")}">Admin</a>'
        )
    return "\n        ".join(parts)


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
        {_build_nav_items()}
      </nav>
      <div class="il-nav-right">
        <span class="il-user-name" title="{_user_name}">{_user_name}</span>
        <a href="?page=logout" target="_self" class="il-signout">Sign Out</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

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
