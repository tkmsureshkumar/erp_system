"""
erp/auth.py — Authentication state helpers for IRONLINE ACCESS ERP.

All functions read from / write to st.session_state.  No I/O is performed
here; the supabase_client is only imported in do_logout() to avoid a
circular-import at module load time.
"""
from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Page registry  (key → display label)
# ---------------------------------------------------------------------------
ALL_PAGES: dict[str, str] = {
    # ── Operations ────────────────────────────────────────────────────────────
    "dashboard":       "Dashboard",
    "customers":       "Customers",
    "sites":           "Sites",
    "operators":       "Operators",
    "machines":        "Machines",
    "assets":          "Assets",
    "machinemovement": "Machine Movement",
    "workorders":      "Work Orders",
    "closeworkorder":  "Close Work Order",
    "deployments":     "Deployments",
    "invoice":         "Invoice",
    "worklog":         "Worklog",
    # ── Reports ───────────────────────────────────────────────────────────────
    "currentdep":      "Active Deployments",
    "fleetstatus":     "Fleet Status",
    "fleetutil":       "Fleet Utilization",
    "machinehistory":  "Machine History",
    "wlreport":        "Worklog Report",
    "woreport":        "Work Order Report",
    "wlreports":       "Worklog Status",
    "custreport":      "Customer Report",
    "opreport":        "Operator Report",
    # ── Config ────────────────────────────────────────────────────────────────
    "system":          "System",
}


# ---------------------------------------------------------------------------
# Session-state helpers
# ---------------------------------------------------------------------------

def is_logged_in() -> bool:
    """Return True if an authenticated user session exists."""
    return bool(st.session_state.get("user"))


def current_user():
    """Return the Supabase auth User object stored in session, or None."""
    return st.session_state.get("user")


def current_profile() -> dict:
    """Return the user_profiles row dict stored in session, or {}."""
    return st.session_state.get("profile") or {}


def is_admin() -> bool:
    """Return True when the current user has the Admin role."""
    return current_profile().get("role") == "Admin"


def record_is_editable(record_status: str | None) -> bool:
    """Return True if a record can be directly edited (Draft or temporarily Unlocked)."""
    return (record_status or "Draft") in ("Draft", "Unlocked")


def has_page_access(page_key: str) -> bool:
    """
    Determine whether the current user may view *page_key*.

    - Admin role: unrestricted access to every page in ALL_PAGES.
    - User role: access is restricted to the labels listed in
      profile["page_access"] (a JSON array of page label strings,
      e.g. ["Dashboard", "Work Orders"]).
    """
    profile = current_profile()
    if profile.get("role") == "Admin":
        return True
    page_label = ALL_PAGES.get(page_key)
    if page_label is None:
        return False
    page_access: list = profile.get("page_access") or []
    return page_label in page_access


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

def do_logout() -> None:
    """
    1. Write a LOGOUT activity log entry.
    2. Sign out from Supabase (invalidates the JWT).
    3. Wipe st.session_state.
    4. Rerun so the login screen is shown.
    """
    # Import here to avoid circular imports at module load.
    from erp.supabase_client import SupabaseClient  # noqa: PLC0415

    try:
        user = current_user()
        profile = current_profile()
        sb = SupabaseClient()
        if user:
            sb.log_activity(
                user_id=user.id,
                user_email=profile.get("email", ""),
                user_name=profile.get("full_name", ""),
                action="LOGOUT",
                module="Auth",
            )
        sb.client.auth.sign_out()
    except Exception:
        # Never block logout due to a logging or network error.
        pass

    # Clear every key so the next rerun shows the login page.
    for key in list(st.session_state.keys()):
        del st.session_state[key]

    st.rerun()
