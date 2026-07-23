"""
erp/views/_lock.py
Shared lifecycle, lock, and approval-workflow UI utilities.

Imported by machine.py, customers.py, site.py, workorder.py,
machinemovement.py, and worklog.py.
"""
from __future__ import annotations

import streamlit as st

from erp import auth
from erp.supabase_client import SupabaseClient

# ── Status styling ─────────────────────────────────────────────────────────────
_STATUS_STYLE: dict[str, tuple[str, str, str]] = {
    # status → (background, text-color, Material Symbol icon)
    "Draft":     ("#FEF3C7", "#92400E", "edit_note"),
    "Locked":    ("#DBEAFE", "#1E40AF", "lock"),
    "Unlocked":  ("#DCFCE7", "#166534", "lock_open"),
    "Cancelled": ("#FEE2E2", "#991B1B", "cancel"),
    "Active":    ("#DCFCE7", "#166534", "check_circle"),
    "Inactive":  ("#F1F5F9", "#6B7280", "block"),
}


def status_chip(status: str | None) -> str:
    """Return an inline HTML status chip (safe to pass to st.markdown unsafe_allow_html)."""
    s = status or "Draft"
    bg, fg, icon = _STATUS_STYLE.get(s, ("#F1F5F9", "#6B7280", "circle"))
    return (
        f"<span style='display:inline-flex;align-items:center;gap:4px;"
        f"padding:3px 10px 3px 7px;border-radius:20px;background:{bg};color:{fg};"
        f"font-size:10px;font-weight:700;letter-spacing:.04em;white-space:nowrap;'>"
        f"<span class='msr' style='font-size:12px;color:{fg};'>{icon}</span>{s}</span>"
    )


def locked_banner() -> None:
    """Show a read-only notice bar. Call at the top of a locked record's detail panel."""
    st.markdown(
        "<div style='display:flex;align-items:center;gap:8px;padding:10px 14px;"
        "background:#DBEAFE;border:1px solid #93C5FD;border-radius:8px;"
        "margin-bottom:12px;font-size:13px;color:#1E40AF;font-weight:600;'>"
        "<span class='msr' style='font-size:18px;color:#2563EB;'>lock</span>"
        "This record is <b>Locked</b>. It is read-only. "
        "Staff may submit an edit request below.</div>",
        unsafe_allow_html=True,
    )


# ── Lifecycle controls ─────────────────────────────────────────────────────────

def lifecycle_controls(
    record_type: str,
    record_id: str,
    record_label: str,
    record_status: str | None,
    *,
    key_prefix: str = "",
) -> str | None:
    """
    Render lifecycle action buttons below a record's save button.

    Admin path:
      Draft / Unlocked  → "Lock Record" button  → returns "Locked"
      Locked            → "Unlock for Edit" button → returns "Unlocked"

    Staff path:
      Draft / Unlocked  → "Submit & Lock" button → returns "Locked"
      Locked            → shows Request Edit form (creates DB row) → returns None

    The caller is responsible for persisting the returned new status to DB
    (e.g., ``sb.update_work_order(record_id, {"record_status": new_status})``).
    """
    status    = record_status or "Draft"
    is_admin  = auth.is_admin()
    st.markdown("<hr style='margin:14px 0 10px;opacity:.15;'>", unsafe_allow_html=True)

    if is_admin:
        if status in ("Draft", "Unlocked"):
            if st.button(
                "🔒  Lock Record",
                key=f"{key_prefix}_lock_btn",
                help="Finalize and lock this record. Staff will need Admin approval to edit.",
            ):
                return "Locked"
        else:
            if st.button(
                "🔓  Unlock for Edit",
                key=f"{key_prefix}_unlock_btn",
                type="secondary",
                help="Temporarily unlock so the record can be edited again.",
            ):
                return "Unlocked"
    else:
        if status in ("Draft", "Unlocked"):
            if st.button(
                "📤  Submit & Lock",
                key=f"{key_prefix}_submit_btn",
                type="primary",
                help="Finalize this record. Once locked, edits require Admin approval.",
            ):
                return "Locked"
        else:
            locked_banner()
            _request_edit_inline(record_type, record_id, record_label, key_prefix=key_prefix)

    return None


def _request_edit_inline(
    record_type: str,
    record_id: str,
    record_label: str,
    *,
    key_prefix: str = "",
) -> None:
    """Inline form for staff to submit an edit request on a locked record."""
    submitted_key = f"{key_prefix}_req_done"

    if st.session_state.get(submitted_key):
        st.success("✔ Edit request already submitted and pending Admin review.")
        return

    with st.expander("✏️  Request Edit from Admin"):
        reason = st.text_area(
            "Reason for edit *",
            key=f"{key_prefix}_req_reason",
            placeholder="Explain clearly why this record needs to be changed…",
            height=100,
        )
        if st.button("Submit Request", key=f"{key_prefix}_req_submit", type="primary"):
            if not (reason or "").strip():
                st.error("A reason is required.")
                return
            try:
                sb      = SupabaseClient()
                user    = auth.current_user()
                profile = auth.current_profile()
                sb.insert_edit_request({
                    "record_type":        record_type,
                    "record_id":          str(record_id),
                    "record_label":       record_label,
                    "request_type":       "EDIT",
                    "requested_by_id":    str(user.id) if user else None,
                    "requested_by_name":  profile.get("full_name") or profile.get("email"),
                    "requested_by_email": profile.get("email"),
                    "reason":             reason.strip(),
                    "status":             "Pending",
                })
                st.session_state[submitted_key] = True
                st.success("✔ Edit request submitted. Admin will review it shortly.")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to submit request: {exc}")


# ── Deactivate / re-activate controls (for master records) ────────────────────

def deactivate_controls(
    entity_label: str,
    record_id: str,
    record_label: str,
    is_active: bool,
    *,
    key_prefix: str = "",
) -> bool | None:
    """
    Render activate / deactivate button for master records
    (machines, customers, sites).

    Returns:
      False  → caller should set is_active=False in DB  (deactivate)
      True   → caller should set is_active=True in DB   (re-activate, admin only)
      None   → no action taken
    """
    st.markdown("<hr style='margin:14px 0 10px;opacity:.15;'>", unsafe_allow_html=True)

    if is_active:
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button(
                f"⛔  Deactivate",
                key=f"{key_prefix}_deact_btn",
                type="secondary",
                use_container_width=True,
                help=f"Mark this {entity_label.lower()} as inactive. "
                     "Record is preserved but hidden from working lists.",
            ):
                return False
    else:
        st.warning(
            f"This {entity_label.lower()} is **Inactive** and hidden from working lists.",
            icon="⚠️",
        )
        if auth.is_admin():
            if st.button(
                f"✅  Re-activate",
                key=f"{key_prefix}_react_btn",
                use_container_width=False,
            ):
                return True

    return None
