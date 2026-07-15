"""
erp/views/admin.py — Admin panel: User management & Activity log.

Only accessible to users whose profile has role == "Admin".
Two tabs:
  1. Users  — create new users, edit permissions / active status.
  2. Activity Log — searchable, filterable audit trail.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from erp import auth
from erp.supabase_client import SupabaseClient


# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
/* ── KPI strip ─────────────────────────────────────────────────────── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    margin: 0 0 28px;
}
.kpi-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 18px 22px 14px;
    position: relative;
    overflow: hidden;
    transition: box-shadow .18s, transform .18s;
}
.kpi-card:hover {
    box-shadow: 0 6px 20px rgba(0,0,0,.08);
    transform: translateY(-2px);
}
.kpi-accent-bar {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 12px 12px 0 0;
}
.kpi-label {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF;
    margin-bottom: 10px;
    display: flex; align-items: center; gap: 6px;
}
.kpi-value {
    font-size: 34px; font-weight: 800;
    color: #111827; line-height: 1;
    margin-bottom: 6px;
    font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: 11px; color: #6B7280; }
.kpi-icon {
    position: absolute; top: 16px; right: 18px;
    font-size: 22px; opacity: .12;
}

/* ── User list cards ─────────────────────────────────────────────────── */
.ul-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 14px 16px;
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 10px;
    transition: box-shadow .16s, border-color .16s;
}
.ul-card:hover {
    box-shadow: 0 4px 16px rgba(37,99,235,.08);
    border-color: #93C5FD;
}
.ul-avatar {
    width: 40px; height: 40px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 800; color: #fff; flex-shrink: 0;
}
.ul-info { flex: 1; min-width: 0; }
.ul-name {
    font-size: 14px; font-weight: 700; color: #111827;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ul-email {
    font-size: 11px; color: #6B7280; margin-top: 2px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ul-badges { display: flex; gap: 6px; flex-shrink: 0; align-items: center; }
.role-badge {
    font-size: 10px; font-weight: 700;
    padding: 2px 10px; border-radius: 20px;
    letter-spacing: .05em; text-transform: uppercase;
}
.role-admin { background: #EDE9FE; color: #5B21B6; border: 1px solid #C4B5FD; }
.role-user  { background: #F1F5F9; color: #334155; border: 1px solid #CBD5E1; }

/* ── Add user banner ─────────────────────────────────────────────────── */
.add-user-banner {
    background: linear-gradient(135deg, #1E2938 0%, #1c3461 100%);
    border-radius: 12px; padding: 16px 20px;
    margin-bottom: 18px;
    display: flex; align-items: center; gap: 14px;
    position: relative; overflow: hidden;
}
.add-user-banner::before {
    content: '';
    position: absolute; top: -30px; right: -30px;
    width: 120px; height: 120px; border-radius: 50%;
    background: rgba(255,255,255,.04);
}
.add-user-banner-icon {
    width: 44px; height: 44px; border-radius: 12px;
    background: rgba(255,255,255,.12);
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; flex-shrink: 0;
}
.add-user-banner-title { font-size: 16px; font-weight: 700; color: #fff; }
.add-user-banner-sub {
    font-size: 11px; color: rgba(255,255,255,.5); margin-top: 2px;
}

/* ── Form sections ───────────────────────────────────────────────────── */
.form-sec-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .13em; text-transform: uppercase;
    color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* ── Log count row ───────────────────────────────────────────────────── */
.log-count {
    font-size: 12px; color: #6B7280;
    margin-bottom: 12px;
    display: flex; align-items: center; gap: 6px;
}
.log-count strong { color: #111827; }

/* ── Tabs polish ─────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0 !important;
    background: transparent !important;
    border-bottom: 2px solid #E2EBF0 !important;
    padding: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    font-size: 12px !important; font-weight: 600 !important;
    color: #6B7280 !important; padding: 8px 18px !important;
    border-radius: 0 !important;
    background: transparent !important; border: none !important;
    margin: 0 !important;
    border-bottom: 2px solid transparent !important;
    transition: color .14s !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #374151 !important; }
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #2563EB !important;
    border-bottom: 2px solid #2563EB !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }
.stTabs [data-baseweb="tab-panel"]     { padding: 18px 0 0 !important; }

/* ── Animations ─────────────────────────────────────────────────────── */
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _initials(name: str) -> str:
    parts = (name or "").strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper() if name else "??"


def _avatar_color(name: str) -> str:
    palette = [
        "#2563EB", "#8B5CF6", "#10B981", "#F59E0B", "#EF4444",
        "#EC4899", "#14B8A6", "#F97316", "#6366F1", "#84CC16",
    ]
    return palette[sum(ord(c) for c in (name or "A")) % len(palette)]


def _kpi_card(icon: str, label: str, value: int | str,
              sub: str = "", accent: str = "#2563EB") -> str:
    return (
        f"<div class='kpi-card'>"
        f"<div class='kpi-accent-bar' style='background:{accent};'></div>"
        f"<span class='kpi-icon msr'>{icon}</span>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div>"
        f"<div class='kpi-sub'>{sub}</div>"
        f"</div>"
    )


def _section_hdr(icon: str, label: str) -> None:
    st.markdown(
        f"<div class='form-sec-hdr'>"
        f"<span class='msr' style='font-size:14px;color:#E87722;'>{icon}</span>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


def _badge(is_active: bool) -> str:
    if is_active:
        return "<span class='badge badge-active'>ACTIVE</span>"
    return "<span class='badge badge-breakdown'>INACTIVE</span>"


def _user_card(u: dict) -> str:
    name     = u.get("full_name") or "—"
    email    = u.get("email") or "—"
    role     = u.get("role") or "User"
    active   = u.get("is_active", True)
    color    = _avatar_color(name)
    role_cls = "role-admin" if role == "Admin" else "role-user"
    return (
        f"<div class='ul-card'>"
        f"<div class='ul-avatar' style='background:{color};'>{_initials(name)}</div>"
        f"<div class='ul-info'>"
        f"<div class='ul-name'>{name}</div>"
        f"<div class='ul-email'>{email}</div>"
        f"</div>"
        f"<div class='ul-badges'>"
        f"<span class='role-badge {role_cls}'>{role}</span>"
        f"{_badge(active)}"
        f"</div>"
        f"</div>"
    )


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    if not auth.is_admin():
        st.error("You don't have access to this page.")
        return

    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # ── Page header ────────────────────────────────────────────────────────────
    st.markdown(
        "<div class='page-eyebrow'>// Administration</div>"
        "<div class='page-title'>Admin Panel</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-bottom:20px'></div>", unsafe_allow_html=True)

    sb      = SupabaseClient()
    user    = auth.current_user()
    profile = auth.current_profile()

    # ── Load users early for KPI strip ────────────────────────────────────────
    try:
        users_list = sb.list_user_profiles()
    except Exception as exc:
        st.error(f"Failed to load users: {exc}")
        users_list = []

    n_total  = len(users_list)
    n_active = sum(1 for u in users_list if u.get("is_active", True))
    n_admin  = sum(1 for u in users_list if u.get("role") == "Admin")

    # ── KPI strip ──────────────────────────────────────────────────────────────
    st.markdown(
        f"<div class='kpi-grid'>"
        + _kpi_card("people",               "Total Users",  n_total,
                    "registered accounts", "#2563EB")
        + _kpi_card("verified_user",         "Active Users", n_active,
                    f"{n_total - n_active} inactive", "#10B981")
        + _kpi_card("admin_panel_settings",  "Admins",       n_admin,
                    "with full access", "#8B5CF6")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Tabs ───────────────────────────────────────────────────────────────────
    tab_users, tab_logs = st.tabs(["👥  Users", "📋  Activity Log"])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — Users
    # ══════════════════════════════════════════════════════════════════════════
    with tab_users:

        # ── Add New User ──────────────────────────────────────────────────────
        with st.expander("＋  Add New User", expanded=False):
            st.markdown(
                "<div class='add-user-banner'>"
                "<div class='add-user-banner-icon'>"
                "<span class='msr' style='color:#fff;font-size:22px;'>person_add</span>"
                "</div>"
                "<div>"
                "<div class='add-user-banner-title'>Create New User</div>"
                "<div class='add-user-banner-sub'>"
                "Fill in the details below to provision a new account."
                "</div>"
                "</div></div>",
                unsafe_allow_html=True,
            )

            with st.form("add_user_form", clear_on_submit=True):
                with st.container(border=True):
                    _section_hdr("person", "Personal Information")
                    col1, col2 = st.columns(2)
                    with col1:
                        new_full_name = st.text_input(
                            "Full Name *", placeholder="Jane Smith"
                        )
                        new_email = st.text_input(
                            "Email Address *", placeholder="jane@example.com"
                        )
                    with col2:
                        new_password = st.text_input(
                            "Password *",
                            type="password",
                            placeholder="Min 6 characters",
                        )
                        new_role = st.selectbox("Role", ["User", "Admin"])

                with st.container(border=True):
                    _section_hdr("lock", "Access Control")
                    new_page_access = st.multiselect(
                        "Page Access",
                        options=list(auth.ALL_PAGES.values()),
                        default=["Dashboard"],
                        help=(
                            "Pages this user can open. "
                            "Ignored for Admin role (admins always see everything)."
                        ),
                    )

                create_submitted = st.form_submit_button(
                    "Create User", type="primary"
                )

            # Handle outside the form context
            if create_submitted:
                if not new_full_name.strip() or not new_email.strip() or not new_password:
                    st.error("Full Name, Email, and Password are required.")
                else:
                    try:
                        created = sb.admin_create_user(
                            email=new_email.strip(),
                            password=new_password,
                            full_name=new_full_name.strip(),
                            role=new_role,
                            page_access=new_page_access,
                        )
                        sb.log_activity(
                            user_id=user.id if user else None,
                            user_email=profile.get("email", ""),
                            user_name=profile.get("full_name", ""),
                            action="CREATE_USER",
                            module="Admin",
                            record_id=created.get("id"),
                            record_label=new_full_name.strip(),
                            details={"email": new_email.strip(), "role": new_role},
                        )
                        st.success(
                            f"User '{new_full_name.strip()}' created successfully."
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to create user: {exc}")

        # ── Existing Users ─────────────────────────────────────────────────────
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        _section_hdr("manage_accounts", f"All Users — {n_total} accounts")

        if not users_list:
            st.info("No user profiles found.")
        else:
            for u in users_list:
                uid     = u.get("id", "")
                uname   = u.get("full_name") or "—"
                urole   = u.get("role") or "User"
                uactive = u.get("is_active", True)
                uaccess: list = u.get("page_access") or []

                st.markdown(_user_card(u), unsafe_allow_html=True)

                with st.expander(f"Edit Permissions — {uname}"):
                    with st.form(f"edit_user_{uid}"):
                        with st.container(border=True):
                            _section_hdr("settings", "Role & Access")
                            ec1, ec2 = st.columns(2)
                            with ec1:
                                edit_role = st.selectbox(
                                    "Role",
                                    ["User", "Admin"],
                                    index=0 if urole == "User" else 1,
                                    key=f"role_sel_{uid}",
                                )
                            with ec2:
                                edit_active = st.checkbox(
                                    "Account Active",
                                    value=uactive,
                                    key=f"active_cb_{uid}",
                                )
                            valid_labels = list(auth.ALL_PAGES.values())
                            current_access_clean = [
                                p for p in uaccess if p in valid_labels
                            ]
                            edit_access = st.multiselect(
                                "Page Access",
                                options=valid_labels,
                                default=current_access_clean,
                                key=f"access_ms_{uid}",
                                help="Applies only when Role is 'User'.",
                            )
                        save_btn = st.form_submit_button(
                            "Save Changes", type="primary"
                        )

                    if save_btn:
                        try:
                            new_payload = {
                                "role": edit_role,
                                "page_access": edit_access,
                                "is_active": edit_active,
                            }
                            sb.update_user_profile(uid, new_payload)
                            sb.log_activity(
                                user_id=user.id if user else None,
                                user_email=profile.get("email", ""),
                                user_name=profile.get("full_name", ""),
                                action="UPDATE_USER",
                                module="Admin",
                                record_id=uid,
                                record_label=uname,
                                details=new_payload,
                            )
                            st.success("Permissions updated successfully.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed to update: {exc}")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — Activity Log
    # ══════════════════════════════════════════════════════════════════════════
    with tab_logs:
        _section_hdr("history", "Activity Log")

        # ── Filter bar ─────────────────────────────────────────────────────────
        with st.container(border=True):
            _section_hdr("filter_list", "Filter Records")

            col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
            with col1:
                MODULE_OPTIONS = [
                    "All", "Auth", "Admin", "Customers", "Sites", "Operators",
                    "Machines", "Assets", "Work Orders", "Deployments", "Worklog",
                ]
                filter_module = st.selectbox(
                    "Module", MODULE_OPTIONS, key="log_filter_module"
                )
            with col2:
                ACTION_OPTIONS = [
                    "All", "LOGIN", "LOGOUT", "CREATE_USER", "UPDATE_USER",
                    "VIEW", "CREATE", "UPDATE", "DELETE",
                ]
                filter_action = st.selectbox(
                    "Action", ACTION_OPTIONS, key="log_filter_action"
                )
            with col3:
                filter_date_from = st.date_input(
                    "From Date", value=None, key="log_filter_from"
                )
            with col4:
                filter_date_to = st.date_input(
                    "To Date", value=None, key="log_filter_to"
                )

            filter_user_name = st.text_input(
                "Search by User Name",
                placeholder="Enter name…",
                key="log_filter_user",
            )

        # ── Data fetch ─────────────────────────────────────────────────────────
        try:
            logs = sb.list_activity_logs(
                module=None if filter_module == "All" else filter_module,
                action=None if filter_action == "All" else filter_action,
                user_name=filter_user_name.strip() or None,
                date_from=filter_date_from or None,
                date_to=filter_date_to or None,
            )
        except Exception as exc:
            st.error(f"Failed to load activity logs: {exc}")
            logs = []

        # ── Log table ──────────────────────────────────────────────────────────
        with st.container(border=True):
            st.markdown(
                f"<div class='log-count'>"
                f"<span class='msr' style='font-size:15px;'>receipt_long</span>"
                f"<strong>{len(logs)}</strong> records found"
                f"</div>",
                unsafe_allow_html=True,
            )

            if logs:
                df = pd.DataFrame(logs)
                display_cols = [
                    c for c in [
                        "created_at", "user_name", "user_email",
                        "action", "module", "record_label", "details",
                    ]
                    if c in df.columns
                ]
                df_display = df[display_cols].copy()
                df_display = df_display.rename(
                    columns={
                        "created_at":   "Timestamp",
                        "user_name":    "User",
                        "user_email":   "Email",
                        "action":       "Action",
                        "module":       "Module",
                        "record_label": "Record",
                        "details":      "Details",
                    }
                )
                if "Timestamp" in df_display.columns:
                    df_display["Timestamp"] = (
                        pd.to_datetime(df_display["Timestamp"], errors="coerce")
                        .dt.strftime("%Y-%m-%d %H:%M:%S")
                        .fillna(df_display["Timestamp"])
                    )
                st.dataframe(df_display, use_container_width=True, hide_index=True)
            else:
                st.info("No activity logs found for the selected filters.")
