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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _badge(is_active: bool) -> str:
    if is_active:
        return (
            '<span style="background:#dcfce7;color:#166534;font-size:11px;'
            'font-weight:700;padding:2px 10px;border-radius:20px;'
            'letter-spacing:.05em;">ACTIVE</span>'
        )
    return (
        '<span style="background:#fee2e2;color:#991b1b;font-size:11px;'
        'font-weight:700;padding:2px 10px;border-radius:20px;'
        'letter-spacing:.05em;">INACTIVE</span>'
    )


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render() -> None:
    if not auth.is_admin():
        st.error("You don't have access to this page.")
        return

    st.markdown(
        """
        <div class="page-eyebrow">// Administration</div>
        <div class="page-title">Admin Panel</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-bottom:20px'></div>", unsafe_allow_html=True)

    sb = SupabaseClient()
    user = auth.current_user()
    profile = auth.current_profile()

    tab_users, tab_logs = st.tabs(["Users", "Activity Log"])

    # ======================================================================
    # TAB 1 — Users
    # ======================================================================
    with tab_users:
        # ── Add New User ──────────────────────────────────────────────────
        with st.expander("Add New User", expanded=False):
            with st.form("add_user_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    new_full_name = st.text_input(
                        "Full Name", placeholder="Jane Smith"
                    )
                    new_email = st.text_input(
                        "Email Address", placeholder="jane@example.com"
                    )
                with col2:
                    new_password = st.text_input(
                        "Password",
                        type="password",
                        placeholder="Min 6 characters",
                    )
                    new_role = st.selectbox("Role", ["User", "Admin"])

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
                    except Exception as exc:
                        st.error(f"Failed to create user: {exc}")

        # ── Existing Users ────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### Existing Users")

        try:
            users_list = sb.list_user_profiles()
        except Exception as exc:
            st.error(f"Failed to load users: {exc}")
            users_list = []

        if not users_list:
            st.info("No user profiles found.")
        else:
            for u in users_list:
                uid = u.get("id", "")
                uname = u.get("full_name") or "—"
                uemail = u.get("email") or "—"
                urole = u.get("role") or "User"
                uactive = u.get("is_active", True)
                uaccess: list = u.get("page_access") or []

                st.markdown(
                    f"""
                    <div style="display:flex;align-items:center;gap:16px;
                                padding:12px 0;border-bottom:1px solid #e5e7eb;">
                      <div style="flex:1;min-width:0;">
                        <span style="font-weight:700;font-size:15px;
                                     color:#111827;">{uname}</span>
                        <span style="color:#6b7280;font-size:13px;
                                     margin-left:12px;">{uemail}</span>
                      </div>
                      <span style="font-size:12px;color:#374151;
                                   background:#f3f4f6;padding:2px 10px;
                                   border-radius:4px;flex-shrink:0;">{urole}</span>
                      {_badge(uactive)}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                with st.expander(f"Edit Permissions — {uname}"):
                    with st.form(f"edit_user_{uid}"):
                        edit_role = st.selectbox(
                            "Role",
                            ["User", "Admin"],
                            index=0 if urole == "User" else 1,
                            key=f"role_sel_{uid}",
                        )
                        # Only show labels that are still valid page keys
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
                        edit_active = st.checkbox(
                            "Account Active",
                            value=uactive,
                            key=f"active_cb_{uid}",
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

    # ======================================================================
    # TAB 2 — Activity Log
    # ======================================================================
    with tab_logs:
        st.markdown("#### Activity Log")

        # Filters
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

        st.markdown(f"**Total records: {len(logs)}**")

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
            # Format timestamp for readability
            if "Timestamp" in df_display.columns:
                df_display["Timestamp"] = (
                    pd.to_datetime(df_display["Timestamp"], errors="coerce")
                    .dt.strftime("%Y-%m-%d %H:%M:%S")
                    .fillna(df_display["Timestamp"])
                )
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("No activity logs found for the selected filters.")
