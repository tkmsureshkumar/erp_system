"""
erp/views/operator.py
Form to add operators and persist only to Supabase.
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from ..models import OperatorStatus
from ..supabase_client import SupabaseClient


def _parse_date(value: str | date | None) -> date | None:
    """Convert string or date to date object."""
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


def render() -> None:
    st.subheader("Operators")

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase client initialization failed. Check your Supabase settings.")
        st.write(str(exc))
        return

    def fetch_operators() -> list[dict[str, object]]:
        try:
            return sb.list_operators()
        except Exception as exc:
            st.error(f"Failed to load operators from Supabase: {exc}")
            return []

    operators = fetch_operators()
    operator_status_values = [e.value for e in OperatorStatus]

    operator_map = {op.get("id"): op for op in operators if op.get("id")}
    operator_ids = [""] + list(operator_map)
    selected_operator_id = st.selectbox(
        "Edit existing operator",
        options=operator_ids,
        format_func=lambda op_id: "New operator" if not op_id else f"{operator_map[op_id].get('operator_name', 'Unknown')} ({op_id})",
        key="selected_operator_id",
    )
    selected_operator = operator_map.get(selected_operator_id)

    if st.session_state.get("editing_operator_id") != selected_operator_id:
        st.session_state["editing_operator_id"] = selected_operator_id
        st.session_state["op_name"] = selected_operator.get("operator_name", "") if selected_operator else ""
        st.session_state["op_mobile"] = selected_operator.get("mobile_number", "") if selected_operator else ""
        st.session_state["op_joining_date"] = _parse_date(selected_operator.get("joining_date")) if selected_operator else None
        st.session_state["op_license_number"] = selected_operator.get("license_number", "") if selected_operator else ""
        st.session_state["op_license_type"] = selected_operator.get("license_type", "") if selected_operator else ""
        st.session_state["op_license_expiry"] = _parse_date(selected_operator.get("license_expiry")) if selected_operator else None
        st.session_state["op_status"] = selected_operator.get("status", OperatorStatus.ACTIVE.value) if selected_operator else OperatorStatus.ACTIVE.value

    with st.form("operator_form"):
        operator_name = st.text_input("Operator Name *", key="op_name")
        mobile_number = st.text_input("Mobile Number", key="op_mobile")
        joining_date = st.date_input("Joining Date", key="op_joining_date")
        status = st.selectbox("Status *", options=operator_status_values, key="op_status")
        license_number = st.text_input("License Number", key="op_license_number")
        license_type = st.text_input("License Type", key="op_license_type")
        license_expiry = st.date_input("License Expiry Date", key="op_license_expiry")

        action_label = "Update Operator" if selected_operator else "Create Operator"
        submit = st.form_submit_button(action_label)
        
        if submit:
            if not operator_name:
                st.error("Operator Name is required.")
            elif not status:
                st.error("Status is required.")
            else:
                payload = dict(
                    operator_name=operator_name,
                    mobile_number=mobile_number or None,
                    joining_date=joining_date.isoformat() if joining_date else None,
                    license_number=license_number or None,
                    license_type=license_type or None,
                    license_expiry=license_expiry.isoformat() if license_expiry else None,
                    status=status,
                )
                try:
                    if selected_operator:
                        sb.update_operator(selected_operator_id, payload)
                        st.success("Operator updated in Supabase.")
                    else:
                        created = sb.insert_operator(payload)
                        identifier = created.get("operator_code") or created.get("id") or operator_name
                        st.success(f"Created operator in Supabase: {identifier}")
                    operators = fetch_operators()
                except Exception as exc:
                    st.error(f"Could not save operator to Supabase: {exc}")

    st.caption("Supabase operators (latest first)")
    if st.button("Refresh from Supabase", key="refresh_operators"):
        operators = fetch_operators()
    
    if operators:
        st.dataframe(
            [
                {
                    "ID": op.get("id", ""),
                    "Code": op.get("operator_code", ""),
                    "Name": op.get("operator_name", ""),
                    "Mobile": op.get("mobile_number", ""),
                    "License": op.get("license_number", ""),
                    "Status": op.get("status", ""),
                }
                for op in operators
            ],
            use_container_width=True,
        )
    else:
        st.info("No operators found.")
