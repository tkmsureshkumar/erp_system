"""
erp/views/machine.py
Form to add and edit machines, persisted to Supabase.
- Machine Type is a DDL sourced from asset_master.
- asset_code is auto-generated as <prefix><seq> (e.g. BL001, BL002).
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from ..models import ConditionStatus, OperationalStatus
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


def _generate_asset_code(prefix: str, existing_machines: list[dict]) -> str:
    """Return the next asset code for the given prefix, e.g. BL003."""
    prefix = (prefix or "M").strip().upper()
    max_seq = 0
    for m in existing_machines:
        code = (m.get("asset_code") or "").strip().upper()
        if code.startswith(prefix):
            suffix = code[len(prefix):]
            if suffix.isdigit():
                max_seq = max(max_seq, int(suffix))
    return f"{prefix}{(max_seq + 1):03d}"


def render() -> None:
    st.markdown(
        """
        <div class="page-eyebrow">// Fleet Operations</div>
        <div class="page-title">Machines</div>
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

    def fetch_machines() -> list[dict]:
        try:
            return sb.list_machines()
        except Exception as exc:
            st.error(f"Failed to load machines from Supabase: {exc}")
            return []

    def fetch_assets() -> list[dict]:
        try:
            return sb.list_assets()
        except Exception as exc:
            st.warning(f"Could not load asset types: {exc}")
            return []

    machines = fetch_machines()
    assets   = fetch_assets()
    operational_status_values = [e.value for e in OperationalStatus]
    condition_status_values   = [e.value for e in ConditionStatus]

    # asset_name → asset_prefix lookup
    asset_type_options: list[str] = [""] + [
        a.get("asset_name", "") for a in assets if a.get("asset_name")
    ]
    asset_prefix_map: dict[str, str] = {
        a.get("asset_name", ""): a.get("asset_prefix", "") for a in assets
    }

    # ── Edit selector ────────────────────────────────────────────────────────
    machine_map = {m.get("id"): m for m in machines if m.get("id")}
    machine_ids = [""] + list(machine_map)
    selected_machine_id = st.selectbox(
        "Edit existing machine",
        options=machine_ids,
        format_func=lambda mid: "New machine" if not mid
            else f"{machine_map[mid].get('asset_code', 'Unknown')} — {machine_map[mid].get('machine_type', '')}",
        key="selected_machine_id",
    )
    selected_machine = machine_map.get(selected_machine_id)

    # ── Sync session state when selection changes ─────────────────────────────
    if st.session_state.get("_editing_machine_id") != selected_machine_id:
        st.session_state["_editing_machine_id"] = selected_machine_id

        current_type = selected_machine.get("machine_type", "") if selected_machine else ""
        st.session_state["m_machine_type"]       = current_type if current_type in asset_type_options else ""
        st.session_state["m_make"]               = selected_machine.get("make", "")           if selected_machine else ""
        st.session_state["m_model"]              = selected_machine.get("model", "")           if selected_machine else ""
        st.session_state["m_serial_number"]      = selected_machine.get("serial_number", "")   if selected_machine else ""
        st.session_state["m_original_yom"]       = selected_machine.get("original_yom") or 0   if selected_machine else 0
        st.session_state["m_operational_yom"]    = str(selected_machine.get("operational_yom", "") or "") if selected_machine else ""
        st.session_state["m_working_capacity"]   = str(selected_machine.get("working_capacity", "") or "") if selected_machine else ""
        st.session_state["m_current_location"]   = selected_machine.get("current_location", "") if selected_machine else ""
        st.session_state["m_purchase_date"]      = _parse_date(selected_machine.get("purchase_date")) if selected_machine else None
        st.session_state["m_purchase_cost"]      = selected_machine.get("purchase_cost") or 0.0 if selected_machine else 0.0
        st.session_state["m_operational_status"] = selected_machine.get("operational_status", OperationalStatus.AVAILABLE.value) if selected_machine else OperationalStatus.AVAILABLE.value
        st.session_state["m_condition_status"]   = selected_machine.get("condition_status", ConditionStatus.RUNNING.value) if selected_machine else ConditionStatus.RUNNING.value

    # ── Machine Type DDL — outside the form so preview updates immediately ───
    machine_type = st.selectbox(
        "Machine Type *",
        options=asset_type_options,
        format_func=lambda v: "Select machine type" if not v
            else (f"{v}  ({asset_prefix_map[v]})" if asset_prefix_map.get(v) else v),
        key="m_machine_type",
    )

    # ── Asset Code preview / display ─────────────────────────────────────────
    if selected_machine:
        # Editing: show the locked-in asset code
        existing_code = selected_machine.get("asset_code", "—")
        st.markdown(
            f"""
            <div style="display:inline-flex;align-items:center;gap:10px;
                        background:#f8fafc;border:1px solid #e2e8f0;
                        border-radius:6px;padding:8px 16px;margin-bottom:8px;">
              <span style="font-size:11px;font-weight:700;letter-spacing:.1em;
                           color:#6b7280;text-transform:uppercase;">Asset Code</span>
              <span style="font-size:18px;font-weight:800;color:#E87722;
                           letter-spacing:.05em;">{existing_code}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif machine_type:
        # New machine: show the next code that will be assigned
        prefix   = asset_prefix_map.get(machine_type, machine_type[:3]).strip().upper()
        preview  = _generate_asset_code(prefix, machines)
        st.markdown(
            f"""
            <div style="display:inline-flex;align-items:center;gap:10px;
                        background:#fff7ed;border:1px solid #fed7aa;
                        border-radius:6px;padding:8px 16px;margin-bottom:8px;">
              <span style="font-size:11px;font-weight:700;letter-spacing:.1em;
                           color:#9a3412;text-transform:uppercase;">Asset Code (auto)</span>
              <span style="font-size:18px;font-weight:800;color:#E87722;
                           letter-spacing:.05em;">{preview}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Form ─────────────────────────────────────────────────────────────────
    with st.form("machine_form"):
        col1, col2 = st.columns(2)
        with col1:
            make          = st.text_input("Make",                           key="m_make")
            serial_number = st.text_input("Serial Number",                  key="m_serial_number")
            original_yom  = st.number_input(
                "Original Year of Manufacture",
                value=int(st.session_state.get("m_original_yom") or 0),
                step=1,
                key="m_original_yom",
            )
            operational_yom = st.text_input(
                "Operational Year of Manufacture",
                key="m_operational_yom",
                placeholder="e.g. 2020",
            )
        with col2:
            model            = st.text_input("Model",            key="m_model")
            working_capacity = st.text_input(
                "Working Capacity",
                key="m_working_capacity",
                placeholder="e.g. 12m / 500kg",
            )
            purchase_date = st.date_input("Purchase Date", key="m_purchase_date")
            purchase_cost = st.number_input(
                "Purchase Cost",
                value=float(st.session_state.get("m_purchase_cost") or 0.0),
                step=0.01,
                key="m_purchase_cost",
            )

        current_location = st.text_input(
            "Current Location",
            key="m_current_location",
            placeholder="e.g. Mumbai Yard",
        )

        col3, col4 = st.columns(2)
        with col3:
            operational_status = st.selectbox(
                "Operational Status *",
                options=operational_status_values,
                key="m_operational_status",
            )
        with col4:
            condition_status = st.selectbox(
                "Condition Status *",
                options=condition_status_values,
                key="m_condition_status",
            )

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
                payload: dict = dict(
                    machine_type=machine_type,
                    make=make or None,
                    model=model or None,
                    serial_number=serial_number or None,
                    original_yom=int(original_yom) if original_yom else None,
                    operational_yom=operational_yom.strip() or None,
                    working_capacity=working_capacity.strip() or None,
                    current_location=current_location.strip() or None,
                    purchase_date=purchase_date.isoformat() if purchase_date else None,
                    purchase_cost=float(purchase_cost) if purchase_cost else None,
                    operational_status=operational_status,
                    condition_status=condition_status,
                )

                if not selected_machine:
                    # Auto-generate asset_code only on creation
                    prefix = asset_prefix_map.get(machine_type, machine_type[:3]).strip().upper()
                    payload["asset_code"] = _generate_asset_code(prefix, machines)

                try:
                    if selected_machine:
                        sb.update_machine(selected_machine_id, payload)
                        st.success("Machine updated in Supabase.")
                    else:
                        created = sb.insert_machine(payload)
                        assigned_code = created.get("asset_code") or payload.get("asset_code", "")
                        st.success(f"Machine created — Asset Code: **{assigned_code}**")
                    machines = fetch_machines()
                except Exception as exc:
                    msg = str(exc)
                    if "23505" in msg and "serial_number" in msg:
                        st.error(
                            "Serial Number already exists. "
                            "Each machine must have a unique serial number."
                        )
                    elif "23505" in msg and "asset_code" in msg:
                        st.error(
                            "Asset Code conflict detected — please refresh and try again."
                        )
                    elif "23505" in msg:
                        st.error(
                            "A duplicate value was detected. "
                            "Please check your input for fields that must be unique."
                        )
                    else:
                        st.error(f"Could not save machine to Supabase: {exc}")

    # ── Machine list ──────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    col_cap, col_btn = st.columns([5, 1])
    with col_cap:
        st.markdown('<p class="filter-label">All Machines</p>', unsafe_allow_html=True)
    with col_btn:
        if st.button("Refresh", key="refresh_machines"):
            machines = fetch_machines()

    if machines:
        st.dataframe(
            [
                {
                    "Asset Code":   m.get("asset_code", ""),
                    "Machine Type": m.get("machine_type", ""),
                    "Make":         m.get("make", ""),
                    "Model":        m.get("model", ""),
                    "Serial No.":   m.get("serial_number", ""),
                    "Orig. YOM":    m.get("original_yom", ""),
                    "Oper. YOM":    m.get("operational_yom", ""),
                    "Capacity":     m.get("working_capacity", ""),
                    "Location":     m.get("current_location", ""),
                    "Operational":  m.get("operational_status", ""),
                    "Condition":    m.get("condition_status", ""),
                }
                for m in machines
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No machines found.")
