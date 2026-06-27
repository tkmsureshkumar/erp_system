"""
erp/views/operator.py
Operator management — modern enterprise UI.
Left:  searchable operator directory.
Right: multi-section form (Personal / Licence / Bank).

Mode state  _op_mode:  "none" | "new" | "edit"
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import streamlit as st

from ..models import OperatorStatus
from ..supabase_client import SupabaseClient

# ── Data helpers ──────────────────────────────────────────────────────────────

def _parse_date(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def _initials(name: str) -> str:
    parts = (name or "").strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper() if name else "??"


def _avatar_color(name: str) -> str:
    palette = ["#0ea5e9", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444",
               "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16"]
    return palette[sum(ord(c) for c in (name or "A")) % len(palette)]


def _section_hdr(title: str, note: str = "") -> None:
    note_html = (
        f"<span style='font-size:11px;color:#6b7280;font-weight:400;"
        f"margin-left:8px;'>{note}</span>" if note else ""
    )
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.12em;"
        f"text-transform:uppercase;color:#E87722;margin-bottom:10px;'>"
        f"{title}{note_html}</div>",
        unsafe_allow_html=True,
    )


def _open_new_form() -> None:
    """Switch UI to new-operator mode and reset form fields."""
    st.session_state["_op_mode"]     = "new"
    st.session_state["_op_sel_id"]   = ""
    st.session_state["_op_sync_key"] = "__new__"
    # Personal
    st.session_state["op_name"]          = ""
    st.session_state["op_mobile"]        = ""
    st.session_state["op_aadhar"]        = ""
    st.session_state["op_joining_date"]  = None
    st.session_state["op_status"]        = OperatorStatus.ACTIVE.value
    # Licence
    st.session_state["op_license_number"]      = ""
    st.session_state["op_license_type"]        = ""
    st.session_state["op_license_expiry"]      = None
    st.session_state["op_heavy_license_start"] = None
    st.session_state["op_light_license_start"] = None
    # Bank
    st.session_state["op_bank_account"]   = ""
    st.session_state["op_ifsc"]           = ""
    st.session_state["op_bank_name"]      = ""
    st.session_state["op_name_passbook"]  = ""
    st.session_state["op_fixed_salary"]   = 0.0


# ── View ──────────────────────────────────────────────────────────────────────

def render() -> None:

    # ── CSS ───────────────────────────────────────────────────────────────────
    st.markdown(
        """
        <style>
        .cust-stat-row {
            display:flex; gap:12px; flex-wrap:wrap; margin:14px 0 20px;
        }
        .cust-stat-pill {
            background:#f8fafc; border:1px solid #e5e7eb;
            border-radius:20px; padding:5px 16px;
            display:flex; align-items:center; gap:6px;
        }
        .cust-stat-val { font-size:15px; font-weight:800; color:#E87722; }
        .cust-stat-lbl { font-size:11px; color:#6b7280; font-weight:500; }

        .cust-banner {
            background:linear-gradient(135deg,#1c1c2e 0%,#2d2d44 100%);
            border-radius:10px; padding:18px 20px; margin-bottom:16px;
            display:flex; align-items:center; gap:14px;
        }
        .cust-banner-avatar {
            width:46px; height:46px; border-radius:50%;
            display:flex; align-items:center; justify-content:center;
            font-size:15px; font-weight:800; color:#fff; flex-shrink:0;
        }
        .cust-banner-name { font-size:19px; font-weight:800; color:#fff; line-height:1.2; }
        .cust-banner-code { font-size:11px; color:rgba(255,255,255,.45);
                            letter-spacing:.08em; margin-top:2px; }
        .badge-new  { background:#dcfce7; color:#166534; font-size:10px; font-weight:700;
                      padding:3px 10px; border-radius:20px; text-transform:uppercase;
                      letter-spacing:.06em; margin-left:auto; white-space:nowrap; }
        .badge-edit { background:#fff7ed; color:#9a3412; font-size:10px; font-weight:700;
                      padding:3px 10px; border-radius:20px; text-transform:uppercase;
                      letter-spacing:.06em; margin-left:auto; white-space:nowrap; }

        .cust-empty {
            background:#f8fafc; border:2px dashed #e5e7eb;
            border-radius:12px; text-align:center;
            padding:60px 32px; color:#9ca3af;
        }
        .cust-empty-icon  { font-size:52px; margin-bottom:14px; }
        .cust-empty-title { font-size:18px; font-weight:700; color:#374151; margin-bottom:8px; }
        .cust-empty-sub   { font-size:13px; margin-bottom:24px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Page header ────────────────────────────────────────────────────────────
    hdr_l, hdr_r = st.columns([5, 1])
    with hdr_l:
        st.markdown(
            "<div class='page-eyebrow'>// Fleet Operations</div>"
            "<div class='page-title'>Operators</div>",
            unsafe_allow_html=True,
        )

    # ── Data load ──────────────────────────────────────────────────────────────
    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error(f"Supabase connection failed: {exc}")
        return

    def fetch_operators() -> list[dict]:
        try:
            return sb.list_operators()
        except Exception as exc:
            st.error(f"Failed to load operators: {exc}")
            return []

    operators    = fetch_operators()
    operator_map = {op["id"]: op for op in operators if op.get("id")}
    operator_status_values = [e.value for e in OperatorStatus]

    # ── Header button ──────────────────────────────────────────────────────────
    with hdr_r:
        st.markdown("<div style='padding-top:18px'></div>", unsafe_allow_html=True)
        if st.button("+ New Operator", use_container_width=True,
                     type="primary", key="hdr_new_op"):
            _open_new_form()
            st.rerun()

    # ── Stats bar ──────────────────────────────────────────────────────────────
    today = date.today()
    expiry_window = today + timedelta(days=90)
    n_operators = len(operators)
    n_active    = sum(1 for op in operators if op.get("status") == OperatorStatus.ACTIVE.value)
    n_expiring  = sum(
        1 for op in operators
        if _parse_date(op.get("license_expiry")) is not None
        and today <= _parse_date(op.get("license_expiry")) <= expiry_window
    )
    st.markdown(
        f"<div class='cust-stat-row'>"
        f"<div class='cust-stat-pill'><span class='cust-stat-val'>{n_operators}</span>"
        f"<span class='cust-stat-lbl'>Total Operators</span></div>"
        f"<div class='cust-stat-pill'><span class='cust-stat-val'>{n_active}</span>"
        f"<span class='cust-stat-lbl'>Active</span></div>"
        f"<div class='cust-stat-pill'><span class='cust-stat-val'>{n_expiring}</span>"
        f"<span class='cust-stat-lbl'>Licence Expiring</span></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Mode / selection state ─────────────────────────────────────────────────
    if "_op_mode" not in st.session_state:
        st.session_state["_op_mode"]   = "none"
    if "_op_sel_id" not in st.session_state:
        st.session_state["_op_sel_id"] = ""

    mode        = st.session_state["_op_mode"]       # "none" | "new" | "edit"
    selected_id = st.session_state["_op_sel_id"]
    selected_operator = operator_map.get(selected_id) if selected_id else None

    # ── Sync form fields when selection or mode changes ────────────────────────
    sync_key = f"{mode}__{selected_id}"
    if st.session_state.get("_op_sync_key") != sync_key:
        st.session_state["_op_sync_key"] = sync_key
        op = selected_operator or {}
        st.session_state["op_name"]          = op.get("operator_name", "")
        st.session_state["op_mobile"]        = op.get("mobile_number", "")
        st.session_state["op_aadhar"]        = op.get("aadhar_number", "")
        st.session_state["op_joining_date"]  = _parse_date(op.get("joining_date"))
        st.session_state["op_status"]        = op.get("status", OperatorStatus.ACTIVE.value)
        st.session_state["op_license_number"]      = op.get("license_number", "")
        st.session_state["op_license_type"]        = op.get("license_type", "")
        st.session_state["op_license_expiry"]      = _parse_date(op.get("license_expiry"))
        st.session_state["op_heavy_license_start"] = _parse_date(op.get("heavy_license_startdate"))
        st.session_state["op_light_license_start"] = _parse_date(op.get("light_license_startdate"))
        st.session_state["op_bank_account"]   = op.get("bank_account_number", "")
        st.session_state["op_ifsc"]           = op.get("ifsc_code", "")
        st.session_state["op_bank_name"]      = op.get("bank_name", "")
        st.session_state["op_name_passbook"]  = op.get("name_in_passbook", "")
        st.session_state["op_fixed_salary"]   = float(op.get("fixed_salary") or 0.0)

    # ── Two-panel layout ───────────────────────────────────────────────────────
    left_col, right_col = st.columns([4, 7], gap="large")

    # ──────────────────────────────────────────────────────────────────────────
    # LEFT — Operator directory
    # ──────────────────────────────────────────────────────────────────────────
    with left_col:
        search_q = st.text_input(
            "search", label_visibility="collapsed",
            placeholder="Search by name or mobile…",
            key="op_search_q",
        )
        q = search_q.strip().lower()
        filtered_map = {
            oid: op for oid, op in operator_map.items()
            if not q
            or q in op.get("operator_name", "").lower()
            or q in op.get("mobile_number", "").lower()
        }

        count_txt = (
            f"{len(filtered_map)} of {n_operators}" if q
            else f"{n_operators} operator{'s' if n_operators != 1 else ''}"
        )
        st.markdown(
            f"<p style='font-size:11px;color:#9ca3af;margin:2px 0 8px;'>{count_txt}</p>",
            unsafe_allow_html=True,
        )

        with st.container(height=530):
            if not filtered_map:
                st.markdown(
                    "<p style='color:#9ca3af;font-size:13px;text-align:center;"
                    "padding:40px 0;'>No matches found.</p>",
                    unsafe_allow_html=True,
                )
            for oid, op in filtered_map.items():
                is_sel   = (oid == selected_id and mode == "edit")
                name     = op.get("operator_name", "Unknown")
                mobile   = op.get("mobile_number", "")
                status_v = op.get("status", "")
                color    = _avatar_color(name)

                sel_border = "border-left:3px solid #E87722;" if is_sel else "border-left:3px solid transparent;"
                sel_bg     = "background:#fff7ed;" if is_sel else "background:#ffffff;"
                name_w     = "font-weight:700;" if is_sel else "font-weight:500;"

                badge_bg  = "#dcfce7" if status_v == OperatorStatus.ACTIVE.value else "#f3f4f6"
                badge_clr = "#166534" if status_v == OperatorStatus.ACTIVE.value else "#6b7280"
                status_badge = (
                    f"<span style='font-size:9px;font-weight:700;background:{badge_bg};"
                    f"color:{badge_clr};padding:2px 7px;border-radius:10px;"
                    f"white-space:nowrap;margin-left:auto;'>{status_v}</span>"
                    if status_v else ""
                )
                st.markdown(
                    f"<div style='{sel_bg}{sel_border}border:1px solid #e5e7eb;"
                    f"padding:9px 12px;display:flex;align-items:center;gap:10px;"
                    f"pointer-events:none;'>"
                    f"<div style='width:34px;height:34px;border-radius:50%;"
                    f"background:{color};display:flex;align-items:center;"
                    f"justify-content:center;font-size:12px;font-weight:800;"
                    f"color:#fff;flex-shrink:0;'>{_initials(name)}</div>"
                    f"<div style='min-width:0;flex:1;'>"
                    f"<div style='font-size:13px;{name_w}color:#111827;"
                    f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{name}</div>"
                    f"<div style='font-size:11px;color:#6b7280;margin-top:1px;'>"
                    f"{mobile or '—'}&nbsp;·&nbsp;{status_v or '—'}</div>"
                    f"</div>{status_badge}</div>",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Selected ✓" if is_sel else "Open",
                    key=f"csel_{oid}",
                    use_container_width=True,
                    help=name,
                ):
                    st.session_state["_op_mode"]     = "edit"
                    st.session_state["_op_sel_id"]   = oid
                    st.session_state["_op_sync_key"] = None   # force sync
                    st.rerun()

    # ──────────────────────────────────────────────────────────────────────────
    # RIGHT — Detail / form panel
    # ──────────────────────────────────────────────────────────────────────────
    with right_col:

        # ── EMPTY STATE ───────────────────────────────────────────────────────
        if mode == "none":
            st.markdown(
                "<div class='cust-empty'>"
                "<div class='cust-empty-icon'>👷</div>"
                "<div class='cust-empty-title'>No operator selected</div>"
                "<p class='cust-empty-sub'>Pick an operator from the directory "
                "or click <strong>+ New Operator</strong> above to add one.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

        # ── NEW / EDIT FORM ───────────────────────────────────────────────────
        else:
            # Header banner
            display_name = (
                st.session_state.get("op_name")
                or (selected_operator.get("operator_name", "") if selected_operator else "")
                or "New Operator"
            )
            col_val = _avatar_color(display_name)
            badge   = (
                "<span class='badge-edit'>Editing</span>"
                if mode == "edit" else "<span class='badge-new'>New Operator</span>"
            )
            st.markdown(
                f"<div class='cust-banner'>"
                f"<div class='cust-banner-avatar' style='background:{col_val};'>"
                f"{_initials(display_name)}</div>"
                f"<div style='flex:1;min-width:0;'>"
                f"<div class='cust-banner-name'>{display_name}</div></div>"
                f"{badge}</div>",
                unsafe_allow_html=True,
            )

            # Section 1 — Personal Details
            with st.container(border=True):
                _section_hdr("Personal Details")
                p1, p2 = st.columns(2)
                with p1:
                    operator_name = st.text_input(
                        "Operator Name *", key="op_name",
                        placeholder="e.g. Vikram Singh",
                    )
                    aadhar_number = st.text_input(
                        "Aadhar Number", key="op_aadhar",
                        placeholder="12-digit Aadhar",
                    )
                with p2:
                    mobile_number = st.text_input(
                        "Mobile Number", key="op_mobile",
                        placeholder="e.g. +91 98111 22233",
                    )
                    joining_date = st.date_input(
                        "Joining Date", key="op_joining_date",
                    )
                status = st.selectbox(
                    "Status", options=operator_status_values, key="op_status",
                )

            # Section 2 — Licence Details
            with st.container(border=True):
                _section_hdr("Licence Details")
                l1, l2 = st.columns(2)
                with l1:
                    license_number = st.text_input(
                        "Driving Licence Number", key="op_license_number",
                    )
                    license_expiry = st.date_input(
                        "Licence Expiry Date", key="op_license_expiry",
                    )
                    light_license_start = st.date_input(
                        "Light Licence Start Date", key="op_light_license_start",
                    )
                with l2:
                    license_type = st.text_input(
                        "Licence Type", key="op_license_type",
                        placeholder="e.g. Boom/Scissor",
                    )
                    heavy_license_start = st.date_input(
                        "Heavy Licence Start Date", key="op_heavy_license_start",
                    )

            # Section 3 — Bank Details
            with st.container(border=True):
                _section_hdr("Bank Details")
                b1, b2 = st.columns(2)
                with b1:
                    bank_account_number = st.text_input(
                        "Account Number", key="op_bank_account",
                        placeholder="e.g. 0012345678901",
                    )
                    bank_name = st.text_input(
                        "Bank Name", key="op_bank_name",
                    )
                    st.number_input(
                        "Fixed Salary",
                        step=0.01,
                        min_value=0.0,
                        key="op_fixed_salary",
                    )
                with b2:
                    ifsc_code = st.text_input(
                        "IFSC Code", key="op_ifsc",
                        placeholder="e.g. SBIN0001234",
                    )
                    name_in_passbook = st.text_input(
                        "Name as per Passbook", key="op_name_passbook",
                    )

            # Action buttons
            sv1, sv2, sv3 = st.columns([4, 1, 1])
            with sv1:
                save_clicked = st.button(
                    "Update Operator" if mode == "edit" else "Create Operator",
                    type="primary",
                    use_container_width=True,
                    key="op_save_btn",
                )
            with sv2:
                if st.button("Cancel", use_container_width=True, key="op_cancel_btn"):
                    st.session_state["_op_mode"]     = "none"
                    st.session_state["_op_sel_id"]   = ""
                    st.session_state["_op_sync_key"] = None
                    st.rerun()
            with sv3:
                if st.button("Refresh", use_container_width=True, key="op_refresh_btn"):
                    st.session_state["_op_sync_key"] = None
                    st.rerun()

            # ── Save logic ─────────────────────────────────────────────────────
            if save_clicked:
                name_val = operator_name.strip()
                if not name_val:
                    st.error("Operator Name is required.")
                else:
                    payload = dict(
                        operator_name=name_val,
                        mobile_number=mobile_number.strip() or None,
                        aadhar_number=aadhar_number.strip() or None,
                        joining_date=joining_date.isoformat() if joining_date else None,
                        status=status,
                        license_number=license_number.strip() or None,
                        license_type=license_type.strip() or None,
                        license_expiry=license_expiry.isoformat() if license_expiry else None,
                        heavy_license_startdate=heavy_license_start.isoformat() if heavy_license_start else None,
                        light_license_startdate=light_license_start.isoformat() if light_license_start else None,
                        bank_account_number=bank_account_number.strip() or None,
                        ifsc_code=ifsc_code.strip() or None,
                        bank_name=bank_name.strip() or None,
                        name_in_passbook=name_in_passbook.strip() or None,
                        fixed_salary=float(st.session_state.get("op_fixed_salary", 0.0)) or None,
                    )

                    _err       = None
                    _toast_msg = None
                    _new_id    = None
                    try:
                        if mode == "edit" and selected_operator:
                            sb.update_operator(selected_id, payload)
                            _toast_msg = f"'{name_val}' updated successfully."
                        else:
                            created    = sb.insert_operator(payload)
                            _new_id    = created.get("id", "")
                            _toast_msg = f"Operator '{name_val}' created."
                    except Exception as exc:
                        _err = str(exc)

                    if _err:
                        st.error(f"Could not save operator: {_err}")
                    else:
                        if _new_id:
                            st.session_state["_op_mode"]     = "edit"
                            st.session_state["_op_sel_id"]   = _new_id
                            st.session_state["_op_sync_key"] = None
                        st.toast(_toast_msg, icon="✅")
                        st.rerun()
