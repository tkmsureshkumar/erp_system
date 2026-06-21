"""
erp/views/machine.py
Form to add machines and persist only to Supabase.
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from ..models import ConditionStatus, OperationalStatus
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
    st.subheader("Machines")

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase client initialization failed. Check your Supabase settings.")
        st.write(str(exc))
        return

    def fetch_machines() -> list[dict[str, object]]:
        try:
            return sb.list_machines()
        except Exception as exc:
            st.error(f"Failed to load machines from Supabase: {exc}")
            return []

    machines = fetch_machines()
    operational_status_values = [e.value for e in OperationalStatus]
    condition_status_values = [e.value for e in ConditionStatus]

    machine_map = {m.get("id"): m for m in machines if m.get("id")}
    machine_ids = [""] + list(machine_map)
    selected_machine_id = st.selectbox(
        "Edit existing machine",
        options=machine_ids,
        format_func=lambda m_id: "New machine" if not m_id else f"{machine_map[m_id].get('asset_code', 'Unknown')} - {machine_map[m_id].get('machine_type', '')} ({m_id})",
        key="selected_machine_id",
    )
    selected_machine = machine_map.get(selected_machine_id)

    if st.session_state.get("editing_machine_id") != selected_machine_id:
        st.session_state["editing_machine_id"] = selected_machine_id
        st.session_state["m_machine_type"] = selected_machine.get("machine_type", "") if selected_machine else ""
        st.session_state["m_make"] = selected_machine.get("make", "") if selected_machine else ""
        st.session_state["m_model"] = selected_machine.get("model", "") if selected_machine else ""
        st.session_state["m_serial_number"] = selected_machine.get("serial_number", "") if selected_machine else ""
        st.session_state["m_original_yom"] = selected_machine.get("original_yom") if selected_machine else None
        st.session_state["m_purchase_date"] = _parse_date(selected_machine.get("purchase_date")) if selected_machine else None
        st.session_state["m_purchase_cost"] = selected_machine.get("purchase_cost") if selected_machine else None
        st.session_state["m_operational_status"] = selected_machine.get("operational_status", OperationalStatus.AVAILABLE.value) if selected_machine else OperationalStatus.AVAILABLE.value
        st.session_state["m_condition_status"] = selected_machine.get("condition_status", ConditionStatus.RUNNING.value) if selected_machine else ConditionStatus.RUNNING.value

    with st.form("machine_form"):
        machine_type = st.text_input("Machine Type *", key="m_machine_type")
        make = st.text_input("Make", key="m_make")
        model = st.text_input("Model", key="m_model")
        serial_number = st.text_input("Serial Number", key="m_serial_number")
        original_yom = st.number_input("Original Year of Manufacture", value=st.session_state.get("m_original_yom") or 0, step=1, key="m_original_yom")
        purchase_date = st.date_input("Purchase Date", key="m_purchase_date")
        purchase_cost = st.number_input("Purchase Cost", value=st.session_state.get("m_purchase_cost") or 0.0, step=0.01, key="m_purchase_cost")
        operational_status = st.selectbox("Operational Status *", options=operational_status_values, key="m_operational_status")
        condition_status = st.selectbox("Condition Status *", options=condition_status_values, key="m_condition_status")

        action_label = "Update Machine" if selected_machine else "Create Machine"
        submit = st.form_submit_button(action_label)

        if submit:
            if not machine_type:
                st.error("Machine Type is required.")
            elif not operational_status:
                st.error("Operational Status is required.")
            elif not condition_status:
                st.error("Condition Status is required.")
            else:
                payload = dict(
                    machine_type=machine_type,
                    make=make or None,
                    model=model or None,
                    serial_number=serial_number or None,
                    original_yom=int(original_yom) if original_yom else None,
                    purchase_date=purchase_date.isoformat() if purchase_date else None,
                    purchase_cost=float(purchase_cost) if purchase_cost else None,
                    operational_status=operational_status,
                    condition_status=condition_status,
                )
                try:
                    if selected_machine:
                        sb.update_machine(selected_machine_id, payload)
                        st.success("Machine updated in Supabase.")
                    else:
                        created = sb.insert_machine(payload)
                        identifier = created.get("asset_code") or created.get("id") or machine_type
                        st.success(f"Created machine in Supabase: {identifier}")
                    machines = fetch_machines()
                except Exception as exc:
                    st.error(f"Could not save machine to Supabase: {exc}")

    st.caption("Supabase machines (latest first)")
    if st.button("Refresh from Supabase", key="refresh_machines"):
        machines = fetch_machines()

    if machines:
        st.dataframe(
            [
                {
                    "ID": m.get("id", ""),
                    "Asset Code": m.get("asset_code", ""),
                    "Machine Type": m.get("machine_type", ""),
                    "Make": m.get("make", ""),
                    "Model": m.get("model", ""),
                    "Serial Number": m.get("serial_number", ""),
                    "Operational Status": m.get("operational_status", ""),
                    "Condition Status": m.get("condition_status", ""),
                }
                for m in machines
            ],
            use_container_width=True,
        )
    else:
        st.info("No machines found.")
