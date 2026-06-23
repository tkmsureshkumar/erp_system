"""
erp/views/operator.py
Manage operators with personal, licence and bank details.
All fields persist to the `operators` Supabase table.
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from ..models import OperatorStatus
from ..supabase_client import SupabaseClient


def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None


def _section(title: str) -> None:
    """Render a lightweight section divider inside the form."""
    st.markdown(
        f"""
        <div style="margin:18px 0 6px;border-top:1px solid #e5e7eb;padding-top:12px;">
          <span style="font-size:10px;font-weight:700;letter-spacing:.12em;
                       color:#E87722;text-transform:uppercase;">{title}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render() -> None:
    st.markdown(
        """
        <div class="page-eyebrow">// Fleet Operations</div>
        <div class="page-title">Operators</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase client initialization failed. Check your Supabase settings.")
        st.write(str(exc))
        return

    def fetch_operators() -> list[dict]:
        try:
            return sb.list_operators()
        except Exception as exc:
            st.error(f"Failed to load operators from Supabase: {exc}")
            return []

    operators             = fetch_operators()
    operator_status_values = [e.value for e in OperatorStatus]

    # ── Edit selector ──────────────────────────────────────────────────────────
    operator_map = {op.get("id"): op for op in operators if op.get("id")}
    operator_ids = [""] + list(operator_map)
    selected_operator_id = st.selectbox(
        "Edit existing operator",
        options=operator_ids,
        format_func=lambda oid: "New operator" if not oid
            else f"{operator_map[oid].get('operator_name', 'Unknown')} ({oid})",
        key="selected_operator_id",
    )
    selected_operator = operator_map.get(selected_operator_id)

    # ── Sync session state when selection changes ──────────────────────────────
    if st.session_state.get("_editing_operator_id") != selected_operator_id:
        st.session_state["_editing_operator_id"] = selected_operator_id
        op = selected_operator or {}

        # Personal
        st.session_state["op_name"]         = op.get("operator_name", "")
        st.session_state["op_mobile"]        = op.get("mobile_number", "")
        st.session_state["op_aadhar"]        = op.get("aadhar_number", "")
        st.session_state["op_joining_date"]  = _parse_date(op.get("joining_date"))
        st.session_state["op_status"]        = op.get("status", OperatorStatus.ACTIVE.value)

        # Licence
        st.session_state["op_license_number"]       = op.get("license_number", "")
        st.session_state["op_license_type"]         = op.get("license_type", "")
        st.session_state["op_license_expiry"]       = _parse_date(op.get("license_expiry"))
        st.session_state["op_heavy_license_start"]  = _parse_date(op.get("heavy_license_startdate"))
        st.session_state["op_light_license_start"]  = _parse_date(op.get("light_license_startdate"))

        # Bank
        st.session_state["op_bank_account"]    = op.get("bank_account_number", "")
        st.session_state["op_ifsc"]            = op.get("ifsc_code", "")
        st.session_state["op_bank_name"]       = op.get("bank_name", "")
        st.session_state["op_name_passbook"]   = op.get("name_in_passbook", "")
        st.session_state["op_fixed_salary"]    = float(op.get("fixed_salary") or 0.0)

    # ── Layout: form left, list right ─────────────────────────────────────────
    col_form, col_list = st.columns([2, 3])

    with col_form:
        with st.form("operator_form"):

            # ── Personal Details ───────────────────────────────────────────────
            _section("Personal Details")

            p1, p2 = st.columns(2)
            with p1:
                operator_name = st.text_input("Operator Name *", key="op_name")
                aadhar_number = st.text_input(
                    "Aadhar Number",
                    key="op_aadhar",
                    placeholder="12-digit Aadhar",
                )
            with p2:
                mobile_number = st.text_input("Mobile Number", key="op_mobile")
                joining_date  = st.date_input("Joining Date", key="op_joining_date")

            status = st.selectbox("Status *", options=operator_status_values, key="op_status")

            # ── Licence Details ────────────────────────────────────────────────
            _section("Licence Details")

            l1, l2 = st.columns(2)
            with l1:
                license_number      = st.text_input("Driving Licence Number", key="op_license_number")
                license_expiry      = st.date_input("Licence Expiry Date",    key="op_license_expiry")
                light_license_start = st.date_input(
                    "Light Licence Start Date",
                    key="op_light_license_start",
                )
            with l2:
                license_type        = st.text_input("Licence Type",            key="op_license_type")
                heavy_license_start = st.date_input(
                    "Heavy Licence Start Date",
                    key="op_heavy_license_start",
                )

            # ── Bank Details ───────────────────────────────────────────────────
            _section("Bank Details")

            b1, b2 = st.columns(2)
            with b1:
                bank_account_number = st.text_input(
                    "Account Number",
                    key="op_bank_account",
                    placeholder="e.g. 0012345678901",
                )
                bank_name = st.text_input("Bank Name", key="op_bank_name")
                fixed_salary = st.number_input(
                    "Fixed Salary",
                    value=float(st.session_state.get("op_fixed_salary", 0.0)),
                    step=0.01,
                    min_value=0.0,
                    key="op_fixed_salary",
                )
            with b2:
                ifsc_code = st.text_input(
                    "IFSC Code",
                    key="op_ifsc",
                    placeholder="e.g. SBIN0001234",
                )
                name_in_passbook = st.text_input(
                    "Name as per Passbook",
                    key="op_name_passbook",
                )

            action_label = "Update Operator" if selected_operator else "Create Operator"
            submitted = st.form_submit_button(action_label)

            if submitted:
                if not operator_name.strip():
                    st.error("Operator Name is required.")
                elif not status:
                    st.error("Status is required.")
                else:
                    payload = dict(
                        # Personal
                        operator_name=operator_name.strip(),
                        mobile_number=mobile_number.strip() or None,
                        aadhar_number=aadhar_number.strip() or None,
                        joining_date=joining_date.isoformat() if joining_date else None,
                        status=status,
                        # Licence
                        license_number=license_number.strip() or None,
                        license_type=license_type.strip() or None,
                        license_expiry=license_expiry.isoformat() if license_expiry else None,
                        heavy_license_startdate=heavy_license_start.isoformat() if heavy_license_start else None,
                        light_license_startdate=light_license_start.isoformat() if light_license_start else None,
                        # Bank
                        bank_account_number=bank_account_number.strip() or None,
                        ifsc_code=ifsc_code.strip() or None,
                        bank_name=bank_name.strip() or None,
                        name_in_passbook=name_in_passbook.strip() or None,
                        fixed_salary=float(fixed_salary) if fixed_salary else None,
                    )
                    try:
                        if selected_operator:
                            sb.update_operator(selected_operator_id, payload)
                            st.success("Operator updated.")
                        else:
                            created = sb.insert_operator(payload)
                            label = created.get("operator_code") or created.get("id") or operator_name
                            st.success(f"Operator created: {label}")
                        operators = fetch_operators()
                    except Exception as exc:
                        st.error(f"Could not save operator: {exc}")

    # ── Operator list ──────────────────────────────────────────────────────────
    with col_list:
        col_cap, col_btn = st.columns([3, 1])
        with col_cap:
            st.markdown('<p class="filter-label">All Operators</p>', unsafe_allow_html=True)
        with col_btn:
            if st.button("Refresh", key="refresh_operators"):
                operators = fetch_operators()

        if operators:
            st.dataframe(
                [
                    {
                        "Code":            op.get("operator_code", ""),
                        "Name":            op.get("operator_name", ""),
                        "Mobile":          op.get("mobile_number", ""),
                        "Aadhar":          op.get("aadhar_number", ""),
                        "Licence No.":     op.get("license_number", ""),
                        "Licence Expiry":  op.get("license_expiry", ""),
                        "Bank A/C":        op.get("bank_account_number", ""),
                        "Bank Name":       op.get("bank_name", ""),
                        "Fixed Salary":    op.get("fixed_salary", ""),
                        "Status":          op.get("status", ""),
                    }
                    for op in operators
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No operators found.")
